from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image
import pandas as pd
import os
import re
import google.generativeai as genai

GEMINI_API_KEY = "AIzaSyDT8wOUCw6-OYJe-n7BbyJJVGxrEUfijac"
genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel('gemini-2.0-flash')

app = Flask(__name__, static_folder='templates', static_url_path='')
CORS(app)

students = []

def extract_student_info(text):
    """Trích xuất thông tin học sinh từ văn bản trả về của Gemini."""
    extracted_students = []
    current_student = {}
    
    name_match = re.search(r'Họ Tên: (.+?)(?:, MSSV:|$)', text)
    if name_match:
        current_student['name'] = name_match.group(1).strip()
    
    id_match = re.search(r'MSSV: (\d+)', text)
    if id_match:
        current_student['id'] = id_match.group(1).strip()
    
    major_match = re.search(r'Ngành: (.+)', text)
    if major_match:
        current_student['major'] = major_match.group(1).strip()
    
    if current_student:
        current_student['id'] = current_student.get('id') or f"AUTO_{len(students) + 1}"
        current_student['name'] = current_student.get('name') or 'Chưa xác định'
        current_student['major'] = current_student.get('major') or 'Chưa xác định'
        current_student['source'] = 'Gemini OCR'
        extracted_students.append(current_student)

    return extracted_students

def extract_grades_info(text):
    """Trích xuất thông tin điểm từ văn bản trả về của Gemini."""
    grades = []
    # Nhận diện dòng: Môn: [Tên môn] - Điểm: [điểm]
    pattern = r'Môn: ([^-\n]+) - Điểm: ([\d\.]+)'
    for match in re.finditer(pattern, text):
        grades.append({
            'subject': match.group(1).strip(),
            'score': match.group(2).strip(),
            'source': 'Gemini OCR'
        })
    return grades

def extract_student_and_grades(text):
    """Trích xuất thông tin học sinh và điểm từ văn bản trả về của Gemini."""
    # Tìm tên học sinh
    name_match = re.search(r'Họ Tên: ([^\n]+)', text)
    name = name_match.group(1).strip() if name_match else 'Chưa xác định'

    # Tìm MSSV
    id_match = re.search(r'MSSV: (\d+)', text)
    student_id = id_match.group(1).strip() if id_match else f"AUTO_{len(students) + 1}"

    # Tìm ngành
    major_match = re.search(r'Ngành: ([^\n]+)', text)
    major = major_match.group(1).strip() if major_match else 'Chưa xác định'

    # Tìm điểm các môn
    grades = []
    pattern = r'Môn: ([^-\n]+) - Điểm: ([\d\.]+)'
    for match in re.finditer(pattern, text):
        grades.append({
            'subject': match.group(1).strip(),
            'score': match.group(2).strip(),
            'source': 'Gemini OCR'
        })

    student = {
        'id': student_id,
        'name': name,
        'major': major,
        'source': 'OCR',
        'grades': grades
    }
    return student

@app.route('/')
def serve_index():
    """Phục vụ file index.html từ thư mục templates."""
    return send_from_directory('templates', 'index.html')

@app.route('/ocr', methods=['POST'])
def run_ocr():
    """API xử lý OCR và trích xuất thông tin học sinh + điểm bằng Gemini."""
    if 'file' not in request.files:
        return jsonify({"error": "Không tìm thấy file"}), 400
    file = request.files['file']
    try:
        image_part = {
            "mime_type": file.mimetype,
            "data": file.read()
        }
        prompt = (
            "Trích xuất thông tin từ ảnh bảng điểm này. "
            "Tìm Họ Tên, MSSV/MSHS, Ngành học và điểm từng môn. "
            "Xuất ra dưới dạng: Họ Tên: [tên], MSSV: [mã số], Ngành: [ngành]. "
            "Sau đó, từng dòng: Môn: [Tên môn] - Điểm: [điểm]. "
            "Nếu không tìm thấy, chỉ cần nói 'Không tìm thấy thông tin'."
        )
        response = model.generate_content([prompt, image_part])
        text = response.text
        student = extract_student_and_grades(text)
        # Nếu chưa có thì thêm vào danh sách
        if not any(s['id'] == student['id'] for s in students):
            students.append(student)
        return jsonify({"raw_text": text, "student": student, "students": students}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/grades', methods=['POST'])
def run_grades_ocr():
    """API xử lý OCR và trích xuất bảng điểm bằng Gemini."""
    if 'file' not in request.files:
        return jsonify({"error": "Không tìm thấy file"}), 400
    file = request.files['file']
    try:
        image_part = {
            "mime_type": file.mimetype,
            "data": file.read()
        }
        prompt = (
            "Trích xuất bảng điểm từ tài liệu này. "
            "Tìm MSSV, Họ Tên, Tên môn học và Điểm. "
            "Xuất ra từng dòng theo dạng: Điểm: [MSSV] - [Tên] - [Môn] - [Điểm]. "
            "Nếu không tìm thấy, chỉ cần nói 'Không tìm thấy bảng điểm'."
        )
        response = model.generate_content([prompt, image_part])
        text = response.text
        grades_info = extract_grades_info(text)
        return jsonify({"raw_text": text, "grades": grades_info}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/students', methods=['GET'])
def get_students():
    """API lấy danh sách học sinh."""
    return jsonify(students)

@app.route('/students', methods=['POST'])
def add_student():
    """API thêm học sinh mới (có thể kèm file bảng điểm)."""
    data = request.form
    new_student = {
        'id': data['id'],
        'name': data['name'],
        'major': data['major'],
        'source': 'Thủ công',
        'grades': []
    }
    if any(s['id'] == new_student['id'] for s in students):
        return jsonify({"error": "Học sinh với mã số này đã tồn tại"}), 409

    # Nếu có file bảng điểm thì đọc và gán vào học sinh
    if 'file' in request.files:
        file = request.files['file']
        image_part = {
            "mime_type": file.mimetype,
            "data": file.read()
        }
        prompt = (
            "Trích xuất bảng điểm các môn từ ảnh này. "
            "Xuất ra từng dòng theo dạng: Môn: [Tên môn] - Điểm: [điểm]. "
            "Nếu có MSSV hoặc tên học sinh thì ghi rõ. Nếu không tìm thấy, chỉ cần nói 'Không tìm thấy bảng điểm'."
        )
        response = model.generate_content([prompt, image_part])
        text = response.text
        grades_info = extract_grades_info(text)
        new_student['grades'] = grades_info

    students.append(new_student)
    return jsonify({"message": "Đã thêm học sinh", "student": new_student}), 201

@app.route('/students/<student_id>', methods=['PUT'])
def update_student(student_id):
    """API cập nhật thông tin học sinh."""
    data = request.json
    for i, student in enumerate(students):
        if student['id'] == student_id:
            if student['id'] != data['id'] and any(s['id'] == data['id'] for s in students):
                 return jsonify({"error": "Mã số mới đã tồn tại"}), 409

            students[i]['name'] = data['name']
            students[i]['major'] = data['major']
            students[i]['id'] = data['id']
            return jsonify({"message": "Đã cập nhật", "student": students[i]}), 200
    return jsonify({"error": "Không tìm thấy học sinh"}), 404

@app.route('/students/<student_id>', methods=['DELETE'])
def delete_student(student_id):
    """API xóa học sinh."""
    global students
    students = [s for s in students if s['id'] != student_id]
    return jsonify({"message": "Đã xóa học sinh"}), 200

@app.route('/export', methods=['GET'])
def export_excel():
    """API xuất dữ liệu ra file Excel (bao gồm điểm)."""
    if not students:
        return jsonify({"error": "Không có dữ liệu"}), 404

    rows = []
    for s in students:
        if s.get('grades'):
            for g in s['grades']:
                rows.append({
                    'MSSV': s['id'],
                    'Họ Tên': s['name'],
                    'Ngành': s['major'],
                    'Môn': g['subject'],
                    'Điểm': g['score'],
                    'Nguồn': s['source']
                })
        else:
            rows.append({
                'MSSV': s['id'],
                'Họ Tên': s['name'],
                'Ngành': s['major'],
                'Môn': '',
                'Điểm': '',
                'Nguồn': s['source']
            })

    df = pd.DataFrame(rows)
    file_path = "danh_sach_hoc_sinh.xlsx"
    df.to_excel(file_path, index=False)
    return send_from_directory('.', file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)