"""
Study Buddy — Streamlit Chat UI
Connects to the FastAPI backend via REST.
"""
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_KEY = os.getenv("AGENT_API_KEY", "my-secret-key-change-in-production")

st.set_page_config(
    page_title="Study Buddy - VGU",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ─── Sidebar ────────────────────────────────────────────────
with st.sidebar:
    st.title("📚 Study Buddy")
    st.caption("Trợ lý học tập AI cho sinh viên VGU")
    st.divider()

    if st.button("🗑️ Xóa hội thoại", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    if st.session_state.get("session_id"):
        sid = st.session_state.session_id
        st.caption(f"Session: `{sid[:8]}…`")

    st.divider()

    # Live health stats from backend
    try:
        health = requests.get(f"{API_URL}/health", timeout=3).json()
        st.metric("Chi phí hôm nay", f"${health.get('daily_cost_usd', 0):.4f}")
        st.metric("Uptime", f"{health.get('uptime_seconds', 0):.0f}s")
        status_color = "🟢" if health.get("agent_ready") else "🔴"
        st.caption(f"{status_color} Agent: {'sẵn sàng' if health.get('agent_ready') else 'chưa cấu hình API key'}")
        st.caption(f"Model: `{health.get('model', '-')}`")
        st.caption(f"Storage: `{health.get('storage', '-')}`")
    except Exception:
        st.warning("⚠️ Không thể kết nối backend")

    st.divider()
    st.caption("Powered by")
    st.caption("Claude (Anthropic) · LangGraph · RAG · FastAPI · Redis")

# ─── Init state ─────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# ─── Main chat ──────────────────────────────────────────────
st.title("💬 Study Buddy")
st.caption("Hỏi về VGU, chương trình học, quy chế, lịch thi, học bổng…")

# Suggested questions
if not st.session_state.messages:
    st.info("💡 **Gợi ý câu hỏi:**\n"
            "- Quy chế thi cử VGU như thế nào?\n"
            "- Làm thế nào để đăng ký học bổng?\n"
            "- Chương trình Khoa học Máy tính gồm những môn gì?\n"
            "- Thủ tục rút môn học như thế nào?")

# Render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Hỏi gì đó… (VD: Điểm GPA tối thiểu để tiếp tục học là bao nhiêu?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Đang tra cứu sổ tay và suy nghĩ…"):
            try:
                resp = requests.post(
                    f"{API_URL}/ask",
                    json={
                        "question": prompt,
                        "session_id": st.session_state.session_id,
                    },
                    headers={"X-API-Key": API_KEY},
                    timeout=90,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.session_id = data["session_id"]
                    answer = data["answer"]
                    st.markdown(answer)
                    st.caption(
                        f"Turn #{data['turn']} · Model: `{data['model']}` · "
                        f"Storage: `{data['storage']}`"
                    )
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                elif resp.status_code == 401:
                    st.error("🔑 API key không hợp lệ.")
                elif resp.status_code == 429:
                    st.warning("⏳ Quá giới hạn yêu cầu. Vui lòng đợi 1 phút rồi thử lại.")
                elif resp.status_code == 503:
                    st.error("🚫 Ngân sách hàng ngày đã hết. Quay lại vào ngày mai.")
                else:
                    st.error(f"Lỗi {resp.status_code}: {resp.text[:200]}")

            except requests.exceptions.ConnectionError:
                st.error("❌ Không thể kết nối với backend. Đảm bảo backend đang chạy.")
            except requests.exceptions.Timeout:
                st.error("⏱️ Timeout — LLM phản hồi quá lâu. Thử lại nhé.")
            except Exception as exc:
                st.error(f"Lỗi không xác định: {exc}")
