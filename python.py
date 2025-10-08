# --- Giao diện và Luồng chính ---

# Lấy API Key
api_key = st.secrets.get("GEMINI_API_KEY")

if not api_key:
     st.error("⚠️ Vui lòng cấu hình Khóa 'GEMINI_API_KEY' trong Streamlit Secrets để sử dụng chức năng AI.")

uploaded_file = st.file_uploader(
    "1. Tải file Word (.docx) chứa Phương án Kinh doanh:",
    type=['docx']
)

# Khởi tạo state để lưu trữ dữ liệu đã trích xuất
if 'extracted_data' not in st.session_state:
    st.session_state['extracted_data'] = None

# --- Chức năng 1: Lọc dữ liệu bằng AI ---
if uploaded_file is not None:
    doc_text = read_docx_file(uploaded_file)
    
    if st.button("Trích xuất Dữ liệu Tài chính bằng AI 🤖"):
        if api_key:
            with st.spinner('Đang đọc và trích xuất thông số tài chính bằng Gemini...'):
                try:
                    st.session_state['extracted_data'] = extract_financial_data(doc_text, api_key)
                    st.success("Trích xuất dữ liệu thành công!")
                except APIError:
                    st.error("Lỗi API: Không thể kết nối hoặc xác thực API Key.")
                except Exception as e:
                    st.error(f"Lỗi trích xuất: {e}")
        else:
            st.error("Vui lòng cung cấp Khóa API.")

# --- Hiển thị và Tính toán (Yêu cầu 2 & 3) ---
if st.session_state['extracted_data'] is not None:
    data = st.session_state['extracted_data']
    
    # ****************** Lọc các giá trị số và xử lý ngoại lệ ******************
    try:
        initial_investment = float(data.get('Vốn đầu tư', 0))
        project_life = int(data.get('Dòng đời dự án', 0))
        annual_revenue = float(data.get('Doanh thu hàng năm', 0))
        annual_cost = float(data.get('Chi phí hoạt động hàng năm', 0))
        wacc = float(data.get('WACC', 0.1)) # Giả định WACC 10% nếu không trích xuất được
        tax_rate = float(data.get('Thuế suất', 0.2)) # Giả định Thuế 20% nếu không trích xuất được
        
        # Đảm bảo WACC và Thuế suất ở dạng thập phân (0 < value < 1)
        if wacc > 1: wacc /= 100
        if tax_rate > 1: tax_rate /= 100
        
    except Exception as e:
        st.error(f"Lỗi chuyển đổi dữ liệu trích xuất thành số: {e}. Vui lòng kiểm tra lại nội dung file Word.")
        initial_investment, project_life, wacc, tax_rate = 0, 0, 0.1, 0.2

    # ****************** Hiển thị Thông số ******************
    st.subheader("2. Các Thông số Dự án đã Trích xuất")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Vốn Đầu tư (C₀)", f"{initial_investment:,.0f} VNĐ")
    col2.metric("Dòng đời dự án (N)", f"{project_life:.0f} năm")
    col3.metric("WACC (k)", f"{wacc:.2%}")
    col1.metric("Doanh thu Hàng năm (R)", f"{annual_revenue:,.0f} VNĐ")
    col2.metric("Chi phí HĐ Hàng năm (C)", f"{annual_cost:,.0f} VNĐ")
    col3.metric("Thuế suất (t)", f"{tax_rate:.2%}")

    st.markdown("---")
    
    # ****************** Bảng Dòng tiền (Yêu cầu 2) ******************
    st.subheader("3. Bảng Dòng tiền (Cash Flow)")
    
    if project_life > 0 and initial_investment >= 0:
        try:
            depreciation = initial_investment / project_life 
        except ZeroDivisionError:
            depreciation = 0

        years = np.arange(1, project_life + 1)
        
        # Tính toán dòng tiền hàng năm (Giả định đơn giản: dòng tiền đều)
        EBT = annual_revenue - annual_cost - depreciation
        Tax = EBT * tax_rate if EBT > 0 else 0
        EAT = EBT - Tax
        # Dòng tiền thuần = Lợi nhuận sau thuế + Khấu hao
        CF = EAT + depreciation
        
        cashflow_data = {
            'Năm': years,
            'Doanh thu (R)': [annual_revenue] * project_life,
            'Chi phí HĐ (C)': [annual_cost] * project_life,
            'Khấu hao (D)': [depreciation] * project_life,
            'Lợi nhuận trước thuế (EBT)': [EBT] * project_life,
            'Thuế (Tax)': [Tax] * project_life,
            'Lợi nhuận sau thuế (EAT)': [EAT] * project_life,
            'Dòng tiền thuần (CF)': [CF] * project_life
        }
        
        df_cashflow = pd.DataFrame(cashflow_data)
        
        st.dataframe(
            df_cashflow.style.format({
                col: '{:,.0f}' for col in df_cashflow.columns if col not in ['Năm']
            }), 
            use_container_width=True
        )

        st.markdown("---")
        
        # ****************** Tính toán Chỉ số (Yêu cầu 3) ******************
st.subheader("4. Các Chỉ số Đánh giá Hiệu quả Dự án")
if wacc > 0:
            try:
                npv, irr, pp, dpp = calculate_project_metrics(df_cashflow, initial_investment, wacc)
                
                metrics_data = {
                    'NPV': npv,
                    'IRR': irr if not np.isnan(irr) else 0, # Dùng 0 để tránh lỗi format
                    'PP': pp,
                    'DPP': dpp
                }
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("NPV (Giá trị hiện tại thuần)", f"{npv:,.0f} VNĐ", delta=("Dự án có lời" if npv > 0 else "Dự án lỗ"))
                col2.metric("IRR (Tỷ suất sinh lời nội tại)", f"{irr:.2%}" if not np.isnan(irr) else "Không tính được")
                col3.metric("PP (Thời gian hoàn vốn)", f"{pp:.2f} năm" if isinstance(pp, float) or isinstance(pp, np.float64) else pp)
                col4.metric("DPP (Hoàn vốn có chiết khấu)", f"{dpp:.2f} năm" if isinstance(dpp, float) or isinstance(dpp, np.float64) else dpp)

                # ****************** Phân tích AI (Yêu cầu 4) ******************
                st.markdown("---")
                st.subheader("5. Phân tích Hiệu quả Dự án (AI)")
                
                if st.button("Yêu cầu AI Phân tích Chỉ số 🧠"):
                    if api_key:
                        with st.spinner('Đang gửi dữ liệu và chờ Gemini phân tích...'):
                            ai_result = get_ai_evaluation(metrics_data, wacc, api_key)
                            st.markdown("**Kết quả Phân tích từ Gemini AI:**")
                            st.info(ai_result)
                    else:
                         st.error("Lỗi: Không tìm thấy Khóa API. Vui lòng kiểm tra cấu hình Secrets.")

            except Exception as e:
                st.error(f"Có lỗi xảy ra khi tính toán chỉ số: {e}. Vui lòng kiểm tra các thông số đầu vào.")
        else:
            st.warning("WACC (Tỷ lệ chiết khấu) phải lớn hơn 0 để tính toán NPV và DPP.")

    else:
        st.warning("Vui lòng đảm bảo Dòng đời Dự án và Vốn Đầu tư đã được trích xuất thành công và có giá trị lớn hơn 0.")

else:
    st.info("Vui lòng tải lên file Word và nhấn nút 'Trích xuất Dữ liệu Tài chính bằng AI' để bắt đầu.")
