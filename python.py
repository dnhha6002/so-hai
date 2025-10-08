# app.py

import streamlit as st
import pandas as pd
import numpy as np
from google import genai
from google.genai.errors import APIError
from docx import Document
import io
import json

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Đánh giá Phương án Kinh doanh (NPV, IRR)",
    layout="wide"
)

st.title("Ứng dụng Đánh giá Phương án Kinh doanh 💰")
st.caption("Sử dụng Gemini AI để trích xuất thông tin từ file Word và phân tích hiệu quả dự án.")

# --- Thiết lập Khóa API (Cập nhật xử lý lỗi ở đây) ---
API_KEY = None
try:
    # 1. Thử lấy từ Streamlit Secrets (cho môi trường Streamlit Cloud)
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    # 2. Hiển thị Lỗi và thêm ô nhập key tạm thời cho môi trường cục bộ
    st.error("""
        **Lỗi Cấu hình: Không tìm thấy Khóa API.** Vui lòng cấu hình Khóa `GEMINI_API_KEY` trong Streamlit Secrets.
        
        Nếu bạn đang chạy ứng dụng cục bộ, bạn có thể **nhập Khóa API tạm thời** dưới đây để thử nghiệm.
        """)
    
    # Thêm sidebar để nhập Khóa API tạm thời
    with st.sidebar:
        st.header("Cấu hình API Key")
        temporary_api_key = st.text_input(
            "Nhập Khóa API của Google Gemini:", 
            type="password"
        )
        if temporary_api_key:
            API_KEY = temporary_api_key
            st.success("Đã nhận Khóa API tạm thời.")
        else:
            st.warning("Vui lòng nhập Khóa API để sử dụng chức năng AI.")

# --- HÀM 1: TRÍCH XUẤT DỮ LIỆU TỪ WORD BẰNG AI (Task 1) ---
def extract_data_from_docx(uploaded_file, api_key):
    """
    Trích xuất nội dung văn bản từ file Word và sử dụng Gemini AI để lọc các chỉ số tài chính.
    """
    # *Đã thêm kiểm tra api_key ngay bên dưới*
    if not api_key:
        return None, "Lỗi API: Không tìm thấy Khóa API. Vui lòng cung cấp key ở Sidebar hoặc Streamlit Secrets."

    try:
        # ... (Phần logic đọc file Word và gọi Gemini API giữ nguyên) ...
        docx_file = io.BytesIO(uploaded_file.getvalue())
        document = Document(docx_file)
        full_text = []
        for para in document.paragraphs:
            full_text.append(para.text)
        text_content = "\n".join(full_text)
        
        if not text_content:
            return None, "File Word không có nội dung."

        # Xây dựng Prompt cho Gemini
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash'
        
        # Định nghĩa cấu trúc JSON mong muốn
        schema = {
            "type": "object",
            "properties": {
                "Vốn đầu tư": {"type": "number", "description": "Tổng vốn đầu tư ban đầu (năm 0)."},
                "Dòng đời dự án": {"type": "integer", "description": "Số năm hoạt động của dự án."},
                "Doanh thu hàng năm": {"type": "array", "items": {"type": "number"}, "description": "Doanh thu dự kiến hàng năm."},
                "Chi phí hoạt động": {"type": "array", "items": {"type": "number"}, "description": "Chi phí hoạt động hàng năm (chưa bao gồm Khấu hao)."},
                "Khấu hao": {"type": "number", "description": "Chi phí khấu hao hàng năm (giả định đều)."},
                "WACC": {"type": "number", "description": "Chi phí vốn bình quân gia quyền (dạng thập phân, ví dụ 0.12 cho 12%)."},
                "Thuế suất": {"type": "number", "description": "Thuế suất thu nhập doanh nghiệp (dạng thập phân, ví dụ 0.20 cho 20%)."}
            },
            "required": ["Vốn đầu tư", "Dòng đời dự án", "Doanh thu hàng năm", "Chi phí hoạt động", "Khấu hao", "WACC", "Thuế suất"]
        }

        prompt = f"""
        Bạn là một chuyên gia phân tích tài chính. Hãy đọc nội dung văn bản dưới đây và trích xuất các thông số tài chính chính của dự án kinh doanh, đặc biệt là các thông số liên quan đến dòng tiền và đánh giá dự án.
        
        Nếu dự án có dòng đời 5 năm, thì 'Doanh thu hàng năm' và 'Chi phí hoạt động' phải là một mảng 5 giá trị tương ứng cho 5 năm. Nếu văn bản chỉ đề cập đến một giá trị chung, hãy lặp lại giá trị đó trong mảng.
        
        NỘI DUNG VĂN BẢN:
        ---
        {text_content}
        ---
        
        Hãy trả lời bằng **DUY NHẤT** một đối tượng JSON tuân thủ schema đã cho.
        """
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"response_mime_type": "application/json", "response_schema": schema}
        )
        
        # Chuyển đổi chuỗi JSON kết quả thành Dict
        extracted_data = json.loads(response.text)
        return extracted_data, "Trích xuất thành công."

    except APIError as e:
        return None, f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except Exception as e:
        return None, f"Đã xảy ra lỗi không xác định khi xử lý file Word hoặc JSON: {e}"


# ... (Các hàm build_cash_flow_table, calculate_project_metrics, analyze_metrics giữ nguyên) ...

# *******************************************************************
# DO CÁC HÀM TÍNH TOÁN (2, 3) VÀ HÀM PHÂN TÍCH (4) KHÔNG ĐỔI
# TÔI SẼ CHỈ HIỂN THỊ PHẦN GIAO DIỆN CHÍNH (MAIN INTERFACE) BỊ ẢNH HƯỞNG
# *******************************************************************

# --- GIAO DIỆN CHÍNH STREAMLIT (Sử dụng lại logic kiểm tra API_KEY) ---

# ... (Phần code các hàm build_cash_flow_table, calculate_project_metrics, analyze_metrics) ...

# --- GIAO DIỆN CHÍNH STREAMLIT ---

# --- Chức năng 1: Tải File Word ---
uploaded_file = st.file_uploader(
    "1. Tải file **Word (.docx)** chứa Phương án Kinh doanh:",
    type=['docx']
)

# Khởi tạo state để lưu dữ liệu đã trích xuất
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None

if uploaded_file is not None:
    # --- Chức năng 1: Nút bấm Trích xuất Dữ liệu ---
    if st.button("Trích xuất Dữ liệu bằng AI 🤖"):
        # Kiểm tra API Key lần nữa trước khi bấm nút
        if not API_KEY:
            st.error("⚠️ Vui lòng cung cấp Khóa API trong thanh Sidebar hoặc Streamlit Secrets để kích hoạt chức năng AI.")
        else:
            with st.spinner('Đang đọc file Word và yêu cầu AI trích xuất dữ liệu...'):
                extracted_data, message = extract_data_from_docx(uploaded_file, API_KEY)
                
                if extracted_data:
                    st.session_state.extracted_data = extracted_data
                    st.success(message)
                    st.toast("Trích xuất thành công!", icon="✅")
                else:
                    st.error(f"Trích xuất thất bại: {message}")
                    st.session_state.extracted_data = None

# ... (Phần hiển thị kết quả Trích xuất, Bảng dòng tiền, Chỉ số Hiệu quả giữ nguyên) ...
