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

# --- Thiết lập Khóa API ---
# Khóa API nên được lưu trữ trong Streamlit Secrets (secrets.toml)
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    API_KEY = None
    st.error("Lỗi: Không tìm thấy Khóa API. Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets.")

# --- HÀM 1: TRÍCH XUẤT DỮ LIỆU TỪ WORD BẰNG AI (Task 1) ---
def extract_data_from_docx(uploaded_file, api_key):
    """
    Trích xuất nội dung văn bản từ file Word và sử dụng Gemini AI để lọc các chỉ số tài chính.
    Kết quả mong muốn là một chuỗi JSON.
    """
    if not api_key:
        return None, "Lỗi API: Không tìm thấy GEMINI_API_KEY."

    try:
        # 1. Đọc nội dung từ file Word
        docx_file = io.BytesIO(uploaded_file.getvalue())
        document = Document(docx_file)
        full_text = []
        for para in document.paragraphs:
            full_text.append(para.text)
        text_content = "\n".join(full_text)
        
        if not text_content:
            return None, "File Word không có nội dung."

        # 2. Xây dựng Prompt cho Gemini
        # Yêu cầu AI trả về kết quả dưới dạng JSON (sử dụng response_schema)
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

# --- HÀM 2: XÂY DỰNG BẢNG DÒNG TIỀN (Task 2) ---
def build_cash_flow_table(data):
    """Xây dựng DataFrame dòng tiền của dự án."""
    T = data['Dòng đời dự án']
    years = np.arange(T + 1)
    
    # Khởi tạo DataFrame
    df = pd.DataFrame({'Năm': years})
    df.set_index('Năm', inplace=True)
    
    # 1. Chi phí Đầu tư Ban đầu (Năm 0)
    df['Đầu tư Ban đầu'] = 0.0
    df.loc[0, 'Đầu tư Ban đầu'] = -data['Vốn đầu tư']
    
    # 2. Dòng tiền Hoạt động (Năm 1 đến T)
    
    # Tạo mảng với giá trị Doanh thu và Chi phí
    doanh_thu_arr = np.array(data['Doanh thu hàng năm'])
    chi_phi_arr = np.array(data['Chi phí hoạt động'])
    
    # Doanh thu và Chi phí bắt đầu từ Năm 1
    df['Doanh thu'] = [0.0] + doanh_thu_arr.tolist()
    df['Chi phí HĐ'] = [0.0] + chi_phi_arr.tolist()
    
    # Giả định Khấu hao đều hàng năm
    khau_hao = data['Khấu hao']
    df['Khấu hao'] = 0.0
    df.loc[1:T, 'Khấu hao'] = khau_hao
    
    # 3. Tính Lợi nhuận trước Thuế (EBT)
    df['EBT'] = df['Doanh thu'] - df['Chi phí HĐ'] - df['Khấu hao']
    
    # 4. Thuế TNDN
    thue_suat = data['Thuế suất']
    # Thuế chỉ tính khi EBT > 0
    df['Thuế'] = np.where(df['EBT'] > 0, -df['EBT'] * thue_suat, 0)
    
    # 5. Lợi nhuận sau Thuế (EAT)
    df['EAT'] = df['EBT'] + df['Thuế'] # EBT - Thuế (Thuế đã là số âm)
    
    # 6. Dòng tiền Ròng (CF)
    # CF = EAT + Khấu hao + Đầu tư ban đầu
    df['Dòng tiền Ròng (CF)'] = df['EAT'] + df['Khấu hao'] + df['Đầu tư Ban đầu']
    
    # Xóa các cột trung gian để bảng CF gọn gàng
    df_cf = df[['Dòng tiền Ròng (CF)']].copy()
    
    return df_cf, df # Trả về cả bảng đầy đủ để tính toán sau này

# --- HÀM 3: TÍNH CÁC CHỈ SỐ (Task 3) ---
def calculate_project_metrics(df_cf, WACC):
    """Tính NPV, IRR, PP và DPP."""
    cash_flows = df_cf['Dòng tiền Ròng (CF)'].values
    T = len(cash_flows) - 1 # Dòng đời dự án
    
    # 1. NPV (Net Present Value)
    npv_value = np.npv(WACC, cash_flows)
    
    # 2. IRR (Internal Rate of Return)
    try:
        irr_value = np.irr(cash_flows)
    except ValueError:
        irr_value = np.nan # Dòng tiền không thay đổi dấu (thường là lỗi)
        
    # 3. PP (Payback Period - Thời gian Hoàn vốn)
    cumulative_cf = np.cumsum(cash_flows)
    
    # Năm mà Cumulative CF chuyển từ âm sang dương
    payback_year_index = np.where(cumulative_cf > 0)[0]
    
    if len(payback_year_index) > 0:
        payback_year = payback_year_index[0]
        # Công thức Nội suy: PP = Năm_hoàn_vốn_trước + |CF tích lũy trước| / CF năm hoàn vốn
        if payback_year == 0:
            pp_value = 0.0 # Hoàn vốn ngay năm 0
        else:
            cf_before = cumulative_cf[payback_year - 1]
            cf_at_payback_year = cash_flows[payback_year]
            pp_value = (payback_year - 1) + abs(cf_before) / cf_at_payback_year
    else:
        pp_value = T + 1 # Không hoàn vốn trong dòng đời dự án
        
    # 4. DPP (Discounted Payback Period - Thời gian Hoàn vốn có chiết khấu)
    discount_factors = 1 / (1 + WACC)**np.arange(T + 1)
    discounted_cf = cash_flows * discount_factors
    cumulative_dcf = np.cumsum(discounted_cf)
    
    dpp_payback_year_index = np.where(cumulative_dcf > 0)[0]
    
    if len(dpp_payback_year_index) > 0:
        dpp_payback_year = dpp_payback_year_index[0]
        if dpp_payback_year == 0:
            dpp_value = 0.0
        else:
            dcf_before = cumulative_dcf[dpp_payback_year - 1]
            dcf_at_payback_year = discounted_cf[dpp_payback_year]
            dpp_value = (dpp_payback_year - 1) + abs(dcf_before) / dcf_at_payback_year
    else:
        dpp_value = T + 1 # Không hoàn vốn có chiết khấu
        
    metrics = {
        'NPV': npv_value,
        'IRR': irr_value,
        'PP': pp_value,
        'DPP': dpp_value
    }
    
    return metrics

# --- HÀM 4: PHÂN TÍCH CHỈ SỐ BỞI AI (Task 4) ---
def analyze_metrics(metrics, project_life, WACC, api_key):
    """Sử dụng Gemini AI để phân tích các chỉ số đánh giá dự án."""
    if not api_key:
        return "Lỗi API: Không tìm thấy GEMINI_API_KEY."

    try:
        client = genai.Client(api_key=api_key)
        model_name = 'gemini-2.5-flash'

        prompt = f"""
        Bạn là một chuyên gia phân tích đầu tư tài chính. Hãy đánh giá tính khả thi của dự án dựa trên các chỉ số sau. 
        Đưa ra nhận xét khách quan, ngắn gọn (khoảng 3-4 đoạn) về việc có nên chấp nhận dự án này hay không.
        
        Các tiêu chí đánh giá:
        - Chấp nhận nếu: NPV > 0 và IRR > WACC.
        - Khuyến nghị: PP và DPP càng ngắn càng tốt (nên ngắn hơn 50% Dòng đời dự án).
        
        Thông số dự án:
        - Dòng đời dự án: {project_life} năm
        - WACC (Tỷ suất chiết khấu): {WACC * 100:.2f}%
        - NPV (Giá trị hiện tại ròng): {metrics['NPV']:,.0f}
        - IRR (Tỷ suất sinh lời nội bộ): {metrics['IRR'] * 100:.2f}%
        - PP (Thời gian hoàn vốn): {metrics['PP']:.2f} năm
        - DPP (Thời gian hoàn vốn có chiết khấu): {metrics['DPP']:.2f} năm
        
        Phân tích:
        """

        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text

    except APIError as e:
        return f"Lỗi gọi Gemini API: Vui lòng kiểm tra Khóa API hoặc giới hạn sử dụng. Chi tiết lỗi: {e}"
    except Exception as e:
        return f"Đã xảy ra lỗi không xác định: {e}"

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
        with st.spinner('Đang đọc file Word và yêu cầu AI trích xuất dữ liệu...'):
            extracted_data, message = extract_data_from_docx(uploaded_file, API_KEY)
            
            if extracted_data:
                st.session_state.extracted_data = extracted_data
                st.success(message)
                st.toast("Trích xuất thành công!", icon="✅")
            else:
                st.error(f"Trích xuất thất bại: {message}")
                st.session_state.extracted_data = None


# --- Hiển thị kết quả Trích xuất và Các bước tiếp theo ---
if st.session_state.extracted_data:
    data = st.session_state.extracted_data
    
    st.subheader("2. Dữ liệu Trích xuất từ AI")
    col_v, col_t, col_wacc = st.columns(3)
    with col_v:
        st.metric("Vốn Đầu tư Ban đầu", f"{data['Vốn đầu tư']:,.0f}")
    with col_t:
        st.metric("Dòng đời Dự án (Năm)", f"{data['Dòng đời dự án']}")
    with col_wacc:
        st.metric("WACC (Tỷ suất chiết khấu)", f"{data['WACC'] * 100:.2f}%")
        
    st.markdown("---")
    
    # Trình bày Doanh thu và Chi phí
    st.info(f"**Doanh thu/Chi phí:** Dự án có dòng đời **{data['Dòng đời dự án']}** năm. Đã trích xuất {len(data['Doanh thu hàng năm'])} giá trị Doanh thu và {len(data['Chi phí hoạt động'])} giá trị Chi phí.")
    
    df_params = pd.DataFrame({
        'Năm': np.arange(1, data['Dòng đời dự án'] + 1),
        'Doanh thu (A)': data['Doanh thu hàng năm'],
        'Chi phí HĐ (B)': data['Chi phí hoạt động'],
        'Khấu hao (C)': [data['Khấu hao']] * data['Dòng đời dự án']
    }).set_index('Năm')
    
    st.dataframe(df_params.style.format('{:,.0f}'), use_container_width=True)

    # --- Chức năng 2: Xây dựng Bảng Dòng Tiền ---
    st.subheader("3. Bảng Dòng tiền Ròng (Cash Flow Table)")
    
    # Kiểm tra tính hợp lệ của dữ liệu trước khi tính toán
    if (data['Dòng đời dự án'] == len(data['Doanh thu hàng năm']) == len(data['Chi phí hoạt động'])):
        try:
            df_cf, df_full = build_cash_flow_table(data)
            
            # Tính Dòng tiền tích lũy và Dòng tiền chiết khấu
            df_full['Dòng tiền Ròng (CF)'].name = 'Dòng tiền Ròng (CF)'
            df_cf['Dòng tiền Ròng (CF)'] = df_full['Dòng tiền Ròng (CF)']
            df_cf['CF Tích lũy'] = df_cf['Dòng tiền Ròng (CF)'].cumsum()
            
            # Thêm cột Dòng tiền chiết khấu (DCF) và DCF tích lũy
            discount_factors = 1 / (1 + data['WACC'])**np.arange(data['Dòng đời dự án'] + 1)
            df_cf['Dòng tiền Chiết khấu (DCF)'] = df_cf['Dòng tiền Ròng (CF)'] * discount_factors
            df_cf['DCF Tích lũy'] = df_cf['Dòng tiền Chiết khấu (DCF)'].cumsum()
            
            st.dataframe(df_cf.style.format('{:,.0f}'), use_container_width=True)
            
            # --- Chức năng 3: Tính toán Các Chỉ số Hiệu quả ---
            st.subheader("4. Các Chỉ số Đánh giá Hiệu quả Dự án")
            metrics = calculate_project_metrics(df_cf, data['WACC'])
            
            # Hiển thị các chỉ số
            col_npv, col_irr, col_pp, col_dpp = st.columns(4)
            with col_npv:
                st.metric("NPV (Giá trị hiện tại ròng)", f"{metrics['NPV']:,.0f}")
            with col_irr:
                st.metric("IRR (Tỷ suất sinh lời nội bộ)", f"{metrics['IRR'] * 100:.2f}%")
            with col_pp:
                st.metric("PP (Thời gian hoàn vốn)", f"{metrics['PP']:.2f} năm")
            with col_dpp:
                st.metric("DPP (Thời gian hoàn vốn CK)", f"{metrics['DPP']:.2f} năm")
            
            st.markdown("---")
            
            # --- Chức năng 4: Phân tích AI ---
            st.subheader("5. Nhận xét Phân tích từ AI (Task 4)")
            if st.button("Yêu cầu AI Phân tích Chỉ số 🧠"):
                with st.spinner('Đang gửi dữ liệu và chờ Gemini phân tích...'):
                    ai_result = analyze_metrics(metrics, data['Dòng đời dự án'], data['WACC'], API_KEY)
                    st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                    st.info(ai_result)
            
        except Exception as e:
            st.error(f"Lỗi xảy ra trong quá trình tính toán: {e}. Vui lòng kiểm tra lại dữ liệu trích xuất.")
            
    else:
        st.warning("Dữ liệu trích xuất không hợp lệ: Số năm của Doanh thu/Chi phí phải bằng Dòng đời Dự án.")

else:
    st.info("Tải file Word lên và bấm nút **Trích xuất Dữ liệu bằng AI 🤖** để bắt đầu.")
