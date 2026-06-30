from __future__ import annotations

import pandas as pd
import streamlit as st
from PIL import Image
from sqlalchemy import select

from services.ai.gemini import GeminiVocabularyExtractor
from services.ai.importer import entries_to_preview_frame, valid_import_rows
from services.database import (
    Deck,
    LANGUAGES,
    SessionLocal,
    User,
    Vocabulary,
    add_vocabulary,
    create_deck,
    due_vocabulary,
    get_decks,
    get_users,
    init_db,
    update_schedule,
)

st.set_page_config(page_title="Rin Anki", page_icon="📚", layout="wide")

@st.cache_resource
def run_db_initialization():
    init_db()

run_db_initialization()

THEMES = {
    "Dịu mắt": {
        "primary": "#0D9488",
        "background": "#F8F6F0",
        "secondary_background": "#EFECE6",
        "text": "#2D2A26",
    },
    "Hồng dịu": {
        "primary": "#DB2777",
        "background": "#FFF5F6",
        "secondary_background": "#FCE7F3",
        "text": "#5F0F40",
    },
    "Tối giản": {
        "primary": "#2DD4BF",
        "background": "#1A1A1E",
        "secondary_background": "#26262B",
        "text": "#E6E5E0",
    },
}


def apply_theme(theme_name: str) -> None:
    theme = THEMES.get(theme_name, THEMES["Dịu mắt"])
    st.markdown(
        f"""
        <style>
        :root {{
            --primary-color: {theme["primary"]} !important;
            --background-color: {theme["background"]} !important;
            --secondary-background-color: {theme["secondary_background"]} !important;
            --text-color: {theme["text"]} !important;
        }}
        .stApp {{
            background-color: var(--background-color) !important;
            color: var(--text-color) !important;
        }}
        [data-testid="stHeader"] {{
            background-color: transparent !important;
        }}
        
        /* Force inputs, textareas, and selectboxes to use secondary theme colors */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] {{
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-color: rgba(128, 128, 128, 0.2) !important;
        }}
        
        /* Style focus state of inputs */
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="input"]:focus-within {{
            border-color: var(--primary-color) !important;
        }}
        
        /* Inner text elements in inputs */
        div[data-baseweb="select"] input,
        div[data-baseweb="input"] input,
        div[data-baseweb="input"] textarea,
        div[data-baseweb="select"] div {{
            color: var(--text-color) !important;
            -webkit-text-fill-color: var(--text-color) !important;
        }}
        
        /* Increment/Decrement buttons in number inputs */
        div[data-testid="stNumberInput"] button {{
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-color: rgba(128, 128, 128, 0.2) !important;
        }}
        
        /* Prevent button text wrapping */
        .stButton > button {{
            white-space: nowrap !important;
            word-break: keep-all !important;
        }}
        
        /* Dropdown popover list styling */
        div[data-baseweb="menu"] {{
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }}
        div[data-baseweb="menu"] li {{
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
        }}
        div[data-baseweb="menu"] li:hover {{
            background-color: var(--primary-color) !important;
            color: var(--background-color) !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

MENU_ITEMS = ["Thêm từ vựng", "Danh sách từ", "Chủ đề", "Quiz", "HDSD"]
USER_DISPLAY_NAMES = {"Rin": "Rin", "Friend": "Châu"}
VOCABULARY_COLUMN_LABELS = {
    "id": "ID",
    "word": "Từ",
    "meaning": "Nghĩa",
    "example": "Ví dụ",
    "note": "Ghi chú",
}


def rerun() -> None:
    st.rerun()


def current_user() -> dict | None:
    return st.session_state.get("user")


def display_user_name(name: str) -> str:
    return USER_DISPLAY_NAMES.get(name, name)


def localized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns=VOCABULARY_COLUMN_LABELS)


def select_user_screen() -> None:
    st.markdown(
        """
        <style>
        .profile-title { text-align:center; margin-top: 8vh; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<h1 class='profile-title'>Ai đang học?</h1>", unsafe_allow_html=True)
    with SessionLocal() as session:
        users = get_users(session)

    columns = st.columns([1, 1], gap="large")
    avatars = {"Rin": "👩", "Châu": "👨"}
    for column, user in zip(columns, users):
        name = display_user_name(user.name)
        with column:
            st.markdown(
                f"""
                <a href="?user_id={user.id}" target="_self" style="text-decoration: none; color: inherit; display: block;">
                    <div style='text-align:center; border:1px solid rgba(128, 128, 128, 0.2); border-radius:8px;
                                background-color: var(--secondary-background-color);
                                padding:36px 16px; margin:24px auto; max-width:240px;
                                cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;'
                                 onmouseover="this.style.transform='scale(1.05)'; this.style.boxShadow='0 4px 15px rgba(0,0,0,0.1)';"
                                 onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='none';">
                        <div style='font-size:72px'>{avatars.get(user.name, "🙂")}</div>
                        <div style='font-size:26px; margin-top:16px; font-weight: 500; color: var(--text-color);'>{name}</div>
                    </div>
                </a>
                """,
                unsafe_allow_html=True,
            )


def deck_selector(session, user_id: int, key: str, label: str = "Chủ đề") -> Deck | None:
    decks = get_decks(session, user_id)
    if not decks:
        st.info("Hãy tạo một chủ đề trước.")
        return None

    deck_ids = [deck.id for deck in decks]
    selected = st.selectbox(
        label,
        deck_ids,
        format_func=lambda deck_id: next(
            f"[{deck.language}] {deck.name}" for deck in decks if deck.id == deck_id
        ),
        key=key,
    )
    return next(deck for deck in decks if deck.id == selected)


def vocabulary_frame(session, deck_id: int, search: str = "") -> pd.DataFrame:
    statement = select(Vocabulary).where(Vocabulary.deck_id == deck_id).order_by(Vocabulary.created_at.desc())
    rows = session.scalars(statement).all()
    frame = pd.DataFrame(
        [
            {
                "id": row.id,
                "word": row.word,
                "meaning": row.meaning,
                "example": row.example,
                "note": row.note,
            }
            for row in rows
        ]
    )
    if search and not frame.empty:
        mask = frame.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        frame = frame[mask]
    return frame


def form_input_ui(session, deck: Deck) -> None:
    st.caption(f"Ngôn ngữ của chủ đề: {deck.language}")
    with st.form("add-word", clear_on_submit=True):
        cols = st.columns([2, 3])
        word = cols[0].text_input("Từ")
        meaning = cols[1].text_input("Nghĩa")
        example = st.text_area("Ví dụ")
        note = st.text_area("Ghi chú")
        submitted = st.form_submit_button("Thêm từ vựng")

    if submitted:
        if not word.strip() or not meaning.strip():
            st.warning("Vui lòng nhập ít nhất từ và nghĩa.")
            return
        add_vocabulary(
            session,
            deck.id,
            {
                "word": word.strip(),
                "meaning": meaning.strip(),
                "example": example.strip(),
                "note": note.strip(),
            },
        )
        st.success("Đã thêm từ vựng.")
        rerun()


def optimize_image(image: Image.Image, max_size: int = 1200, quality: int = 80) -> Image.Image:
    # Convert RGBA/P to RGB if necessary (JPEG doesn't support transparency)
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    
    # Resize if any dimension is larger than max_size
    width, height = image.size
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int(height * (max_size / width))
        else:
            new_height = max_size
            new_width = int(width * (max_size / height))
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Compress the image by saving as JPEG to BytesIO
    from io import BytesIO
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)
    return Image.open(buffer)


def ai_import_ui(session, deck: Deck) -> None:
    st.caption(f"Ngôn ngữ của chủ đề: {deck.language}")
    mode = st.radio("Nguồn dữ liệu", ["Quét ảnh viết tay", "Dán văn bản"], horizontal=True)
    entries = None

    try:
        if mode == "Quét ảnh viết tay":
            if st.session_state.get("clear_pasted"):
                st.session_state.pasted_image_base64 = ""
                st.session_state.clear_pasted = False

            # Paste image from clipboard container (hidden from view)
            st.markdown(
                """
                <style>
                .st-key-pasted_image_base64 {
                    display: none !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            pasted_base64 = st.text_area("Pasted Base64", key="pasted_image_base64")

            # Side-by-side: File Uploader and Paste Zone
            col_upload, col_paste = st.columns(2)
            with col_upload:
                uploaded_image = st.file_uploader("Tải ảnh lên", type=["jpg", "jpeg", "png", "webp"])
            with col_paste:
                st.components.v1.html(
                    """
                    <div id="paste-zone" tabindex="0" style="
                        border: 2px dashed rgba(128, 128, 128, 0.4);
                        border-radius: 8px;
                        padding: 16px 12px;
                        text-align: center;
                        color: var(--text-color, #2D2A26);
                        background-color: var(--secondary-background-color, #EFECE6);
                        cursor: pointer;
                        font-family: sans-serif;
                        font-size: 14px;
                        font-weight: 500;
                        outline: none;
                        transition: border-color 0.2s;
                        height: 52px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        box-sizing: border-box;
                    ">
                        📋 Bấm vào đây & nhấn Ctrl + V để dán ảnh
                    </div>
                    <script>
                        const zone = document.getElementById('paste-zone');
                        
                        try {
                            const parentStyle = window.parent.getComputedStyle(window.parent.document.body);
                            zone.style.color = parentStyle.getPropertyValue('--text-color');
                            zone.style.backgroundColor = parentStyle.getPropertyValue('--secondary-background-color');
                            
                            zone.addEventListener('focus', () => {
                                zone.style.borderColor = parentStyle.getPropertyValue('--primary-color');
                            });
                            zone.addEventListener('blur', () => {
                                zone.style.borderColor = 'rgba(128, 128, 128, 0.4)';
                            });
                        } catch (e) {
                            console.error("Failed to copy style properties:", e);
                        }

                        const handlePaste = (e) => {
                            console.log("Paste event triggered on element", e.currentTarget, e);
                            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
                            console.log("Clipboard items list:", items);
                            for (let i = 0; i < items.length; i++) {
                                if (items[i].type.indexOf('image') !== -1) {
                                    console.log("Image format detected in clipboard item:", items[i].type);
                                    const blob = items[i].getAsFile();
                                    const reader = new FileReader();
                                    reader.onload = (event) => {
                                        const base64Data = event.target.result;
                                        console.log("Base64 conversion successful. Data length:", base64Data.length);
                                        const textarea = window.parent.document.querySelector('.st-key-pasted_image_base64 textarea');
                                        if (textarea) {
                                            console.log("Writing base64 image data to parent textarea using React prototype value setter...");
                                            const nativeTextAreaValueSetter = Object.getOwnPropertyDescriptor(
                                                window.HTMLTextAreaElement.prototype,
                                                'value'
                                            ).set;
                                            nativeTextAreaValueSetter.call(textarea, base64Data);
                                            
                                            // 1. Dispatch input event to update React local state
                                            textarea.dispatchEvent(new Event('input', { bubbles: true }));
                                            
                                            // 2. Dispatch change event
                                            textarea.dispatchEvent(new Event('change', { bubbles: true }));
                                            
                                            // 3. Dispatch blur event to trigger Streamlit's state sync to Python
                                            textarea.dispatchEvent(new Event('blur', { bubbles: true }));
                                            
                                            // 4. Dispatch Ctrl+Enter keydown event to force submission
                                            const keydownEvent = new KeyboardEvent('keydown', {
                                                key: 'Enter',
                                                code: 'Enter',
                                                keyCode: 13,
                                                which: 13,
                                                ctrlKey: true,
                                                metaKey: true,
                                                bubbles: true,
                                                cancelable: true
                                            });
                                            textarea.dispatchEvent(keydownEvent);
                                            
                                            console.log("All events (input, change, blur, Ctrl+Enter keydown) dispatched successfully.");
                                        } else {
                                            console.error("Target textarea (.st-key-pasted_image_base64 textarea) not found in parent document!");
                                        }
                                    };
                                    reader.readAsDataURL(blob);
                                    e.preventDefault();
                                    break;
                                }
                            }
                        };

                        // Listen locally in the iframe
                        zone.addEventListener('paste', handlePaste);
                        console.log("Local paste listener registered on iframe zone.");

                        // Listen globally on the parent window's document to catch Ctrl+V anywhere
                        try {
                            if (window.parent && window.parent.document) {
                                // Prevent duplicates by removing the previous handler stored on parent window
                                if (window.parent.__rin_anki_paste_handler__) {
                                    window.parent.document.removeEventListener('paste', window.parent.__rin_anki_paste_handler__);
                                    console.log("Previous global paste handler removed from parent document.");
                                }
                                
                                // Save current handler reference globally
                                window.parent.__rin_anki_paste_handler__ = handlePaste;
                                
                                // Register new handler
                                window.parent.document.addEventListener('paste', handlePaste);
                                console.log("New global paste listener registered on parent document.");
                            }
                        } catch (err) {
                            console.error("Global paste listener attachment failed:", err);
                        }
                    </script>
                    """,
                    height=90,
                )

            image = None
            if uploaded_image is not None:
                image = Image.open(uploaded_image)
            elif pasted_base64:
                try:
                    import base64
                    from io import BytesIO
                    img_data = base64.b64decode(pasted_base64.split(",")[1])
                    image = Image.open(BytesIO(img_data))
                except Exception as e:
                    st.error(f"Lỗi đọc ảnh từ clipboard: {e}")

            if image is not None:
                st.image(image, width=420)
                
                if pasted_base64:
                    if st.button("Xóa ảnh đã dán", use_container_width=True):
                        st.session_state.clear_pasted = True
                        st.rerun()

                if st.button("Quét bằng AI"):
                    with st.spinner("Đang trích xuất từ vựng bằng Gemini..."):
                        optimized_image = optimize_image(image)
                        entries = GeminiVocabularyExtractor().extract_from_image(optimized_image)
        else:
            pasted = st.text_area("Dán ghi chú")
            if st.button("Phân tích bằng AI") and pasted.strip():
                with st.spinner("Đang trích xuất từ vựng bằng Gemini..."):
                    entries = GeminiVocabularyExtractor().extract_from_text(pasted)
    except Exception as exc:
        st.error(str(exc))

    if entries is not None:
        st.session_state.ai_preview = entries_to_preview_frame(entries)

    preview = st.session_state.get("ai_preview")
    if preview is not None and not preview.empty:
        st.subheader("Xem trước trước khi nhập")
        st.caption("Các dòng cần kiểm tra là những dòng có độ tin cậy dưới 0.7.")
        preview_for_editor = preview.drop(columns=["language"], errors="ignore")
        edited = st.data_editor(
            preview_for_editor,
            hide_index=True,
            use_container_width=True,
            column_config={
                "import": st.column_config.CheckboxColumn("Nhập"),
                "word": st.column_config.TextColumn("Từ"),
                "meaning": st.column_config.TextColumn("Nghĩa"),
                "example": st.column_config.TextColumn("Ví dụ"),
                "note": st.column_config.TextColumn("Ghi chú"),
                "confidence": st.column_config.NumberColumn("Độ tin cậy", min_value=0.0, max_value=1.0),
                "needs_review": st.column_config.CheckboxColumn("Cần kiểm tra"),
            },
            disabled=["confidence", "needs_review"],
            key="ai-preview-editor",
        )
        edited["language"] = deck.language
        rows = valid_import_rows(edited)
        if st.button("Nhập các dòng đã chọn"):
            for row in rows:
                add_vocabulary(session, deck.id, row)
            st.session_state.pop("ai_preview", None)
            st.success(f"Đã nhập {len(rows)} dòng.")
            rerun()


def add_vocabulary_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("Thêm từ vựng")

    with SessionLocal() as session:
        with st.expander("Thêm chủ đề", expanded=False):
            with st.form("create-topic-from-add", clear_on_submit=True):
                topic_language = st.selectbox("Ngôn ngữ", LANGUAGES, key="add_topic_language")
                topic_name = st.text_input("Tên chủ đề mới")
                if st.form_submit_button("Tạo chủ đề") and topic_name.strip():
                    create_deck(session, user["id"], topic_name, topic_language)
                    st.success("Đã tạo chủ đề.")
                    rerun()

        deck = deck_selector(session, user["id"], key="add_deck_id", label="Thêm vào chủ đề")
        if deck is None:
            return

        input_mode = st.radio("Cách thêm", ["Nhập bằng AI", "Form input"], horizontal=True)
        if input_mode == "Nhập bằng AI":
            ai_import_ui(session, deck)
        else:
            form_input_ui(session, deck)


def word_list_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("Danh sách từ")

    with SessionLocal() as session:
        deck = deck_selector(session, user["id"], key="list_deck_id", label="Lọc theo chủ đề")
        if deck is None:
            return

        search = st.text_input("Tìm kiếm trong chủ đề")
        frame = vocabulary_frame(session, deck.id, search)
        st.dataframe(localized_frame(frame), hide_index=True, use_container_width=True)

        if frame.empty:
            return

        st.subheader("Sửa hoặc xóa từ")
        vocab_id = st.selectbox(
            "Chọn từ",
            frame["id"].tolist(),
            format_func=lambda item_id: frame.loc[frame["id"] == item_id, "word"].iloc[0],
        )
        vocab = session.get(Vocabulary, int(vocab_id))
        if vocab is None:
            return

        with st.form("edit-word"):
            word = st.text_input("Từ", value=vocab.word)
            meaning = st.text_input("Nghĩa", value=vocab.meaning)
            example = st.text_area("Ví dụ", value=vocab.example)
            note = st.text_area("Ghi chú", value=vocab.note)
            save, delete_word = st.columns(2)
            should_save = save.form_submit_button("Lưu")
            should_delete = delete_word.form_submit_button("Xóa")

        if should_save:
            vocab.language = deck.language
            vocab.word = word.strip()
            vocab.meaning = meaning.strip()
            vocab.example = example.strip()
            vocab.note = note.strip()
            session.commit()
            st.success("Đã lưu thay đổi.")
            rerun()
        if should_delete:
            session.delete(vocab)
            session.commit()
            st.success("Đã xóa từ.")
            rerun()


def topic_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("Chủ đề")

    with SessionLocal() as session:
        decks = get_decks(session, user["id"])
        if decks:
            st.dataframe(
                pd.DataFrame(
                    [
                        {"id": deck.id, "Ngôn ngữ": deck.language, "Chủ đề": deck.name}
                        for deck in decks
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )

        with st.form("create-deck", clear_on_submit=True):
            language = st.selectbox("Ngôn ngữ", LANGUAGES, key="topic_language")
            name = st.text_input("Tên chủ đề mới", placeholder="Ví dụ: Bài 2, TOPIK I, Business English")
            if st.form_submit_button("Tạo chủ đề") and name.strip():
                create_deck(session, user["id"], name, language)
                rerun()

        deck = deck_selector(session, user["id"], key="manage_deck_id", label="Chủ đề cần quản lý")
        if deck is None:
            return

        new_language = st.selectbox("Ngôn ngữ", LANGUAGES, index=LANGUAGES.index(deck.language))
        new_name = st.text_input("Tên mới", value=deck.name)
        left, right = st.columns(2)
        if left.button("Đổi tên", use_container_width=True) and new_name.strip():
            old_language = deck.language
            deck.language = new_language
            deck.name = new_name.strip()
            if old_language != new_language:
                for vocab in deck.vocabulary:
                    vocab.language = new_language
            session.commit()
            rerun()
        if right.button("Xóa chủ đề", use_container_width=True):
            session.delete(deck)
            session.commit()
            st.session_state.pop("manage_deck_id", None)
            rerun()


def quiz_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("Quiz")

    with SessionLocal() as session:
        deck = deck_selector(session, user["id"], key="quiz_deck_id", label="Chủ đề")
        if deck is None:
            return

        question_count = st.number_input("Số câu hỏi", min_value=1, max_value=100, value=20)
        if st.button("Bắt đầu quiz"):
            cards = due_vocabulary(session, deck.id, int(question_count))
            st.session_state.quiz = {
                "cards": [card.id for card in cards],
                "index": 0,
                "show_answer": False,
            }
            if not cards:
                st.info("Hiện chưa có thẻ nào đến hạn ôn.")
            else:
                rerun()

        quiz = st.session_state.get("quiz")
        if not quiz or not quiz.get("cards"):
            return

        if quiz["index"] >= len(quiz["cards"]):
            st.success("Đã hoàn thành lượt quiz.")
            if st.button("Xóa lượt quiz"):
                st.session_state.pop("quiz", None)
                rerun()
            return

        vocab = session.get(Vocabulary, quiz["cards"][quiz["index"]])
        if vocab is None:
            quiz["index"] += 1
            rerun()

        st.caption(f"Câu {quiz['index'] + 1} / {len(quiz['cards'])}")
        st.markdown(
            f"""
            <div style='border:1px solid rgba(128, 128, 128, 0.2); border-radius:8px; padding:32px; text-align:center; background-color: var(--secondary-background-color);'>
                <div style='font-size:48px; font-weight:700; color: var(--text-color);'>{vocab.word}</div>
                <div style='margin-top:8px; color: var(--text-color); opacity: 0.7;'>{deck.language}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if not quiz["show_answer"]:
            if st.button("Hiện đáp án", use_container_width=True):
                quiz["show_answer"] = True
                rerun()
            return

        st.markdown(f"### {vocab.meaning}")
        if vocab.example:
            st.write(vocab.example)
        if vocab.note:
            st.info(vocab.note)

        left, middle, right = st.columns(3)
        actions = [
            (left, "😵 Chưa nhớ", "forgot"),
            (middle, "🤔 Nhớ sơ sơ", "partial"),
            (right, "😄 Nhớ rồi", "remembered"),
        ]
        for column, label, result in actions:
            if column.button(label, use_container_width=True):
                update_schedule(session, vocab.id, result)
                quiz["index"] += 1
                quiz["show_answer"] = False
                rerun()


def hdsd_screen() -> None:
    st.title("📚 Hướng dẫn sử dụng Rin Anki")
    st.markdown(
        """
        Chào mừng bạn đến với **Rin Anki** - ứng dụng ôn tập từ vựng khoa học kết hợp phương pháp Lặp lại ngắt quãng (Spaced Repetition) và AI trợ lý Gemini.
        """
    )

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.subheader("💡 Các chức năng chính")
        with st.expander("📝 1. Thêm Từ Vựng", expanded=True):
            st.markdown(
                """
                Có 2 cách linh hoạt để nạp từ mới:
                * **Form Input**: Nhập thủ công từ, nghĩa, ví dụ và ghi chú.
                * **Nhập bằng AI (Gemini)**:
                    * **Quét ảnh viết tay**: Upload ảnh chụp tập từ vựng, Gemini sẽ tự động bóc tách từ, nghĩa, ví dụ.
                    * **Dán ghi chú**: Dán văn bản thô bất kỳ, AI sẽ phân tách thành các mục tương ứng.
                    * *Mẹo*: Bạn có thể kiểm tra và chỉnh sửa lại dữ liệu trong bảng xem trước trước khi bấm lưu chính thức.
                """
            )
        with st.expander("🗂️ 2. Quản Lý Chủ Đề"):
            st.markdown(
                """
                * Mỗi chủ đề sẽ đi kèm ngôn ngữ đích cụ thể (Hàn - KR, Anh - EN, Nhật - JP, Trung - CN) để tối ưu hóa hiển thị.
                * Có thể tự do sửa tên, đổi ngôn ngữ hoặc xóa chủ đề khi hoàn tất.
                """
            )
        with st.expander("📋 3. Tra Cứu & Chỉnh Sửa"):
            st.markdown(
                """
                * Vào mục **Danh sách từ** để tra cứu toàn bộ từ vựng đã lưu.
                * Tìm kiếm thông minh theo từ hoặc nghĩa gốc.
                * Hỗ trợ sửa chi tiết hoặc xóa hẳn từ vựng khỏi cơ sở dữ liệu.
                """
            )

    with col2:
        st.subheader("🧠 Cơ chế Ôn tập (Quiz)")
        st.markdown(
            """
            Ứng dụng mô phỏng thuật toán **Spaced Repetition** (Lặp lại ngắt quãng) của Anki:
            * Hệ thống tự động tính toán thời gian đến hạn ôn tập dựa trên câu trả lời của bạn.
            * Nhìn từ vựng ➔ Tự đoán nghĩa ➔ Bấm **Hiện đáp án** ➔ Đánh giá mức độ ghi nhớ.
            """
        )
        st.info(
            """
            **Chu kỳ ôn tập:**
            1. **😵 Chưa nhớ**: Xem lại sau **15 phút**.
            2. **🤔 Nhớ sơ sơ**: Xem lại sau **2 giờ**.
            3. **😄 Nhớ rồi**: Chu kỳ giãn cách tăng dần: **7 ngày ➜ 14 ngày ➜ 30 ngày ➜ 60 ngày ➜ 90 ngày**.
            """
        )

        st.subheader("🎨 Giao diện & Tiện ích")
        st.markdown(
            """
            * **Đổi giao diện**: Tích hợp 3 bộ màu dịu nhẹ bảo vệ mắt:
                * **Dịu mắt** (Màu kem/teal nhã nhặn).
                * **Hồng dịu** (Màu hồng rose/plum ấm áp).
                * **Tối giản** (Nền tối charcoal dịu mắt ban đêm).
            * **Lưu trạng thái**: Tự động giữ phiên đăng nhập và giao diện khi F5 (tải lại trang).
            """
        )


def render_top_bar() -> str:
    user = current_user()
    assert user is not None

    left, middle, right = st.columns([5.0, 1.5, 1.5])
    with left:
        st.markdown(f"### Anki · {display_user_name(user['name'])}")
    with middle:
        theme_options = list(THEMES.keys())
        selected_theme = st.selectbox(
            "Giao diện",
            theme_options,
            index=theme_options.index(st.session_state.theme),
            label_visibility="collapsed",
            key="theme_selector",
        )
        if selected_theme != st.session_state.theme:
            st.session_state.theme = selected_theme
            with SessionLocal() as session:
                db_user = session.get(User, user["id"])
                if db_user:
                    db_user.theme = selected_theme
                    session.commit()
            rerun()
    with right:
        if st.button("Đổi người học"):
            st.session_state.clear()
            st.query_params.clear()
            rerun()

    # Determine default menu index from query parameters
    default_menu = st.query_params.get("menu", "Thêm từ vựng")
    if default_menu not in MENU_ITEMS:
        default_menu = "Thêm từ vựng"
    default_index = MENU_ITEMS.index(default_menu)

    selected_menu = st.radio(
        "Menu",
        MENU_ITEMS,
        index=default_index,
        horizontal=True,
        label_visibility="collapsed",
        key="menu_radio",
    )

    if st.query_params.get("menu") != selected_menu:
        st.query_params["menu"] = selected_menu
        rerun()

    return selected_menu


def main() -> None:
    if "theme" not in st.session_state:
        st.session_state.theme = "Dịu mắt"

    # Check query parameters for session persistence (F5)
    query_user_id = st.query_params.get("user_id")
    if query_user_id:
        try:
            uid = int(query_user_id)
            if not st.session_state.get("user") or st.session_state.user["id"] != uid:
                with SessionLocal() as session:
                    db_user = session.get(User, uid)
                    if db_user:
                        st.session_state.user = {"id": db_user.id, "name": db_user.name}
                        st.session_state.theme = db_user.theme or "Dịu mắt"
        except ValueError:
            pass

    apply_theme(st.session_state.theme)

    if current_user() is None:
        select_user_screen()
        return

    page = render_top_bar()
    if page == "Thêm từ vựng":
        add_vocabulary_screen()
    elif page == "Danh sách từ":
        word_list_screen()
    elif page == "Chủ đề":
        topic_screen()
    elif page == "Quiz":
        quiz_screen()
    else:
        hdsd_screen()


if __name__ == "__main__":
    main()
