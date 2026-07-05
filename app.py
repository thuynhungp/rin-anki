from __future__ import annotations

import sys
# Clear cached local services modules to force Streamlit Cloud to reload them when app.py runs
for mod in list(sys.modules.keys()):
    if mod.startswith("services.") or mod == "services":
        sys.modules.pop(mod, None)

from datetime import datetime
import random
import pandas as pd
import streamlit as st
from PIL import Image
from sqlalchemy import select

from services.ai.gemini import GeminiVocabularyExtractor
from services.ai.grammar_agent import GrammarAgent
from services.ai.importer import entries_to_preview_frame, valid_import_rows
from services.database import (
    Deck,
    LANGUAGES,
    SessionLocal,
    User,
    Vocabulary,
    GrammarNote,
    GrammarTag,
    add_vocabulary,
    check_vocabulary_exists,
    create_deck,
    due_vocabulary,
    due_vocabulary_cards,
    get_decks,
    get_users,
    init_db,
    update_schedule,
    save_quiz_results,
    get_grammar_notes,
    create_grammar_note,
    update_grammar_note,
    delete_grammar_note,
    reorder_grammar_note,
    get_user_tags,
    set_note_tags,
)

st.set_page_config(page_title="Rin Anki", page_icon="📚", layout="wide")

@st.cache_resource
def run_init_db():
    init_db()

run_init_db()

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
        
        /* Force inputs, textareas, file uploaders, and selectboxes to use secondary theme colors */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="input"],
        div[data-baseweb="textarea"] > div,
        div[data-baseweb="textarea"],
        .stTextInput input,
        .stTextArea textarea,
        .stSelectbox div,
        div[data-testid="stFileUploader"] section,
        div[data-testid="stFileUploaderFile"],
        div[data-testid="stFileUploaderFile"] > div {{
            background-color: var(--secondary-background-color) !important;
            color: var(--text-color) !important;
            border-color: rgba(128, 128, 128, 0.2) !important;
        }}
        
        /* Style focus state of inputs */
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="textarea"]:focus-within,
        .stTextInput input:focus,
        .stTextArea textarea:focus {{
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

        /* Prevent global fade out / gray out of components during rerun / loading */
        [data-stale="true"] {{
            opacity: 1 !important;
            filter: none !important;
        }}
        [data-stale="true"] * {{
            opacity: 1 !important;
            filter: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def get_allowed_languages(user_name: str) -> list[str]:
    if user_name == "Rin":
        return ["KR"]
    elif user_name == "Friend":
        return ["EN", "JP", "CN"]
    return LANGUAGES


MENU_ITEMS = ["Thêm từ vựng", "Danh sách từ", "Chủ đề", "Ghi chú ngữ pháp", "Quiz", "HDSD"]
USER_DISPLAY_NAMES = {"Rin": "Rin", "Friend": "Châu"}
VOCABULARY_COLUMN_LABELS = {
    "id": "ID",
    "word": "Từ",
    "meaning": "Nghĩa",
    "example": "Ví dụ",
    "note": "Ghi chú",
    "conjugation_a_eo_yeo": "아/어/여",
    "conjugation_eun_neun": "은/n는",
    "conjugation_eu_ni_kka": "(으)니까",
}


def rerun() -> None:
    st.rerun()


def current_user() -> dict | None:
    return st.session_state.get("user")


def display_user_name(name: str) -> str:
    return USER_DISPLAY_NAMES.get(name, name)


def localized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns=VOCABULARY_COLUMN_LABELS)


def display_custom_table(df: pd.DataFrame, localize: bool = True) -> None:
    table_df = localized_frame(df) if localize else df
    html_table = table_df.to_html(index=False, classes="custom-theme-table")
    st.markdown(
        f"""<style>
.custom-table-container {{
    width: 100%;
    max-height: 450px;
    overflow-x: auto;
    overflow-y: auto;
    border: 1px solid rgba(128, 128, 128, 0.2);
    border-radius: 8px;
    margin-bottom: 20px;
}}
table.custom-theme-table {{
    width: 100%;
    border-collapse: collapse;
    font-family: inherit;
    background-color: var(--secondary-background-color) !important;
    color: var(--text-color) !important;
}}
table.custom-theme-table th {{
    position: -webkit-sticky;
    position: sticky;
    top: 0;
    z-index: 2;
    background-color: var(--primary-color) !important;
    color: var(--background-color) !important;
    font-weight: 600;
    text-align: left;
    padding: 12px;
    border-bottom: 2px solid rgba(128, 128, 128, 0.3);
}}
table.custom-theme-table td {{
    padding: 12px;
    border-bottom: 1px solid rgba(128, 128, 128, 0.15);
    vertical-align: middle;
}}
table.custom-theme-table tr:hover {{
    background-color: rgba(128, 128, 128, 0.05);
}}
</style>
<div class="custom-table-container">
    {html_table}
</div>""",
        unsafe_allow_html=True
    )


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
    avatars = {"Rin": "🗿", "Châu": "🥴"}
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
                        <div style='font-size:72px'>{avatars.get(name, "🙂")}</div>
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
    statement = select(Vocabulary).where(Vocabulary.deck_id == deck_id).order_by(Vocabulary.created_at.asc(), Vocabulary.id.asc())
    rows = session.scalars(statement).all()
    
    deck = session.get(Deck, deck_id)
    is_kr = deck is not None and deck.language == "KR"
    
    frame_data = []
    for index, row in enumerate(rows):
        item = {
            "db_id": row.id,
            "id": index + 1,
            "word": row.word,
            "meaning": row.meaning,
            "note": row.note,
            "example": row.example,
        }
        if is_kr:
            conj = row.conjugation_data
            item["conjugation_a_eo_yeo"] = conj.get("a_eo_yeo", "")
            item["conjugation_eun_neun"] = conj.get("eun_neun", "")
            item["conjugation_eu_ni_kka"] = conj.get("eu_ni_kka", "")
        frame_data.append(item)
        
    frame = pd.DataFrame(frame_data)
    
    if search and not frame.empty:
        search_cols = ["word", "meaning", "example", "note"]
        if is_kr:
            search_cols.extend(["conjugation_a_eo_yeo", "conjugation_eun_neun", "conjugation_eu_ni_kka"])
        search_cols = [c for c in search_cols if c in frame.columns]
        mask = frame[search_cols].astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        frame = frame[mask]
    return frame


def vocabulary_by_language_frame(session, user_id: int, language: str, search: str = "") -> pd.DataFrame:
    statement = (
        select(Vocabulary)
        .join(Deck)
        .where(Deck.user_id == user_id, Vocabulary.language == language)
        .order_by(Vocabulary.created_at.asc(), Vocabulary.id.asc())
    )
    rows = session.scalars(statement).all()
    
    is_kr = language == "KR"
    
    frame_data = []
    for index, row in enumerate(rows):
        item = {
            "db_id": row.id,
            "id": index + 1,
            "Chủ đề": row.deck.name,
            "word": row.word,
            "meaning": row.meaning,
            "note": row.note,
            "example": row.example,
        }
        if is_kr:
            conj = row.conjugation_data
            item["conjugation_a_eo_yeo"] = conj.get("a_eo_yeo", "")
            item["conjugation_eun_neun"] = conj.get("eun_neun", "")
            item["conjugation_eu_ni_kka"] = conj.get("eu_ni_kka", "")
        frame_data.append(item)
        
    frame = pd.DataFrame(frame_data)
    
    if search and not frame.empty:
        search_cols = ["word", "meaning", "example", "note", "Chủ đề"]
        if is_kr:
            search_cols.extend(["conjugation_a_eo_yeo", "conjugation_eun_neun", "conjugation_eu_ni_kka"])
        search_cols = [c for c in search_cols if c in frame.columns]
        mask = frame[search_cols].astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        frame = frame[mask]
    return frame


def form_input_ui(session, deck: Deck) -> None:
    st.caption(f"Ngôn ngữ của chủ đề: {deck.language}")
    with st.form("add-word", clear_on_submit=True):
        cols = st.columns([2, 3])
        word = cols[0].text_input("Từ")
        meaning = cols[1].text_input("Nghĩa")
        note = st.text_area("Ghi chú")
        example = st.text_area("Ví dụ")
        submitted = st.form_submit_button("Thêm từ vựng")

    if submitted:
        word_clean = word.strip()
        meaning_clean = meaning.strip()
        if not word_clean or not meaning_clean:
            st.warning("Vui lòng nhập ít nhất từ và nghĩa.")
            return
        
        if check_vocabulary_exists(session, deck.id, word_clean):
            st.warning(f"Từ '{word_clean}' đã tồn tại trong chủ đề '{deck.name}'.")
            return

        add_vocabulary(
            session,
            deck.id,
            {
                "word": word_clean,
                "meaning": meaning_clean,
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
                st.session_state.pop("pasted_image_base64", None)
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
            col_upload, col_paste = st.columns(2, vertical_alignment="bottom")
            with col_upload:
                uploaded_image = st.file_uploader("Tải ảnh lên", type=["jpg", "jpeg", "png", "webp"])
            with col_paste:
                st.components.v1.html(
                    """
                    <style>
                        html, body {
                            margin: 0;
                            padding: 0;
                            height: 100%;
                            overflow: hidden;
                        }
                    </style>
                    <div id="paste-zone" tabindex="0" style="
                        border: 2px dashed rgba(128, 128, 128, 0.4);
                        border-radius: 8px;
                        padding: 16px 12px;
                        text-align: center;
                        color: var(--text-color, #2D2A26);
                        background-color: var(--secondary-background-color, rgba(128, 128, 128, 0.1));
                        cursor: pointer;
                        font-family: sans-serif;
                        font-size: 14px;
                        font-weight: 500;
                        outline: none;
                        transition: border-color 0.2s;
                        height: 100%;
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
                            const parentStyle = window.parent.getComputedStyle(window.parent.document.documentElement);
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
                                // Prevent duplicates by removing previous handlers stored on parent window
                                if (window.parent.__rin_anki_paste_handler__) {
                                    window.parent.document.removeEventListener('paste', window.parent.__rin_anki_paste_handler__);
                                }
                                if (window.parent.__rin_anki_vocab_paste_handler__) {
                                    window.parent.document.removeEventListener('paste', window.parent.__rin_anki_vocab_paste_handler__);
                                }
                                if (window.parent.__rin_anki_note_paste_handler__) {
                                    window.parent.document.removeEventListener('paste', window.parent.__rin_anki_note_paste_handler__);
                                }
                                
                                // Save current handler reference globally
                                window.parent.__rin_anki_vocab_paste_handler__ = handlePaste;
                                
                                // Register new handler
                                window.parent.document.addEventListener('paste', handlePaste);
                                console.log("New global vocab paste listener registered on parent document.");
                            }
                        } catch (err) {
                            console.error("Global paste listener attachment failed:", err);
                        }
                    </script>
                    """,
                    height=75,
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
            added_count = 0
            skipped_words = []
            for row in rows:
                word_clean = row["word"].strip()
                if check_vocabulary_exists(session, deck.id, word_clean):
                    skipped_words.append(word_clean)
                else:
                    add_vocabulary(session, deck.id, row)
                    added_count += 1
            st.session_state.pop("ai_preview", None)
            if added_count > 0:
                st.success(f"Đã nhập thành công {added_count} từ.")
            if skipped_words:
                st.warning(f"Bỏ qua {len(skipped_words)} từ đã tồn tại: {', '.join(skipped_words)}")
            rerun()


def add_vocabulary_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("Thêm từ vựng")

    with SessionLocal() as session:
        with st.expander("Thêm chủ đề", expanded=False):
            with st.form("create-topic-from-add", clear_on_submit=True):
                allowed_langs = get_allowed_languages(user["name"])
                topic_language = st.selectbox("Ngôn ngữ", allowed_langs, key="add_topic_language")
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
        filter_mode = st.radio("Chế độ lọc", ["Theo chủ đề", "Theo ngôn ngữ"], horizontal=True)
        
        deck = None
        selected_lang = None
        current_lang = ""
        
        if filter_mode == "Theo chủ đề":
            deck = deck_selector(session, user["id"], key="list_deck_id", label="Lọc theo chủ đề")
            if deck is None:
                return
            current_lang = deck.language
            search = st.text_input("Tìm kiếm trong chủ đề")
        else:
            allowed_langs = get_allowed_languages(user["name"])
            selected_lang = st.selectbox("Chọn ngôn ngữ", allowed_langs, key="list_language")
            current_lang = selected_lang
            search = st.text_input(f"Tìm kiếm từ tiếng {selected_lang}")
        
        # Smart conjugation check and bulk update UI for Korean decks
        if current_lang == "KR":
            if filter_mode == "Theo chủ đề":
                all_vocabs = deck.vocabulary
            else:
                statement = (
                    select(Vocabulary)
                    .join(Deck)
                    .where(Deck.user_id == user["id"], Vocabulary.language == "KR")
                )
                all_vocabs = list(session.scalars(statement).all())
                
            unconjugated_vocabs = []
            for vocab in all_vocabs:
                word = vocab.word.strip()
                if word.endswith("다"):
                    conj = vocab.conjugation_data
                    if not conj or not conj.get("a_eo_yeo") or not conj.get("eun_neun") or not conj.get("eu_ni_kka"):
                        unconjugated_vocabs.append(vocab)
            
            if all_vocabs:
                col_bulk_left, col_bulk_right = st.columns([3, 1], vertical_alignment="center")
                with col_bulk_left:
                    st.info(f"Có {len(unconjugated_vocabs)} động từ/tính từ tiếng Hàn chưa chia động từ (trong tổng số {len(all_vocabs)} từ).")
                with col_bulk_right:
                    overwrite = st.checkbox("Ghi đè từ đã chia", value=False)
                
                if st.button("Tự động chia động từ (AI)", use_container_width=True):
                    to_conjugate = all_vocabs if overwrite else unconjugated_vocabs
                    # Filter: only words ending in "다" (Korean verbs/adjectives)
                    to_conjugate = [v for v in to_conjugate if v.word.strip().endswith("다")]
                    
                    if not to_conjugate:
                        st.info("Không có động từ/tính từ nào cần chia.")
                    else:
                        with st.spinner("Đang chia động từ bằng AI..."):
                            words_to_query = [v.word.strip() for v in to_conjugate]
                            
                            # Call Gemini in batches of 50
                            batch_size = 50
                            results = []
                            extractor = GeminiVocabularyExtractor()
                            for i in range(0, len(words_to_query), batch_size):
                                batch = words_to_query[i:i+batch_size]
                                try:
                                    batch_results = extractor.conjugate_korean_words(batch)
                                    results.extend(batch_results)
                                except Exception as e:
                                    st.error(f"Lỗi khi chia động từ: {e}")
                                    break
                            
                            # Match results to database
                            updated_count = 0
                            result_map = {res["word"]: res for res in results if "word" in res}
                            for vocab in to_conjugate:
                                w = vocab.word.strip()
                                if w in result_map:
                                    res = result_map[w]
                                    vocab.conjugation_data = {
                                        "a_eo_yeo": res.get("a_eo_yeo") or "",
                                        "eun_neun": res.get("eun_neun") or "",
                                        "eu_ni_kka": res.get("eu_ni_kka") or "",
                                    }
                                    updated_count += 1
                            
                            session.commit()
                            st.success(f"Đã cập nhật thành công {updated_count} từ!")
                            rerun()
 
        if filter_mode == "Theo chủ đề":
            frame = vocabulary_frame(session, deck.id, search)
        else:
            frame = vocabulary_by_language_frame(session, user["id"], selected_lang, search)
            
        display_frame = frame.drop(columns=["db_id"]) if "db_id" in frame.columns else frame
        if current_lang == "KR" and "note" in display_frame.columns:
            display_frame = display_frame.drop(columns=["note"])
        display_custom_table(display_frame)
 
        if frame.empty:
            return
 
        st.subheader("Sửa hoặc xóa từ")
        vocab_id = st.selectbox(
            "Chọn từ",
            frame["db_id"].tolist(),
            format_func=lambda d_id: f"{frame.loc[frame['db_id'] == d_id, 'id'].iloc[0]}. {frame.loc[frame['db_id'] == d_id, 'word'].iloc[0]}",
        )
        vocab = session.get(Vocabulary, int(vocab_id))
        if vocab is None:
            return
 
        with st.form("edit-word"):
            word = st.text_input("Từ", value=vocab.word)
            meaning = st.text_input("Nghĩa", value=vocab.meaning)
            note = st.text_area("Ghi chú", value=vocab.note)
            example = st.text_area("Ví dụ", value=vocab.example)
            
            # Show and edit conjugation forms for Korean deck
            if vocab.language == "KR":
                conj = vocab.conjugation_data
                c_a_eo_yeo = st.text_input("아/어/여", value=conj.get("a_eo_yeo", ""))
                c_eun_neun = st.text_input("은/는", value=conj.get("eun_neun", ""))
                c_eu_ni_kka = st.text_input("(으)니까", value=conj.get("eu_ni_kka", ""))
                
            save, delete_word = st.columns(2)
            should_save = save.form_submit_button("Lưu")
            should_delete = delete_word.form_submit_button("Xóa")
 
        if should_save:
            vocab.language = vocab.deck.language
            vocab.word = word.strip()
            vocab.meaning = meaning.strip()
            vocab.example = example.strip()
            vocab.note = note.strip()
            if vocab.language == "KR":
                vocab.conjugation_data = {
                    "a_eo_yeo": c_a_eo_yeo.strip(),
                    "eun_neun": c_eun_neun.strip(),
                    "eu_ni_kka": c_eu_ni_kka.strip(),
                }
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
            display_custom_table(
                pd.DataFrame(
                    [
                        {"id": deck.id, "Ngôn ngữ": deck.language, "Chủ đề": deck.name}
                        for deck in decks
                    ]
                ),
                localize=False
            )

        with st.form("create-deck", clear_on_submit=True):
            allowed_langs = get_allowed_languages(user["name"])
            language = st.selectbox("Ngôn ngữ", allowed_langs, key="topic_language")
            name = st.text_input("Tên chủ đề mới", placeholder="Ví dụ: Bài 2, TOPIK I, Business English")
            if st.form_submit_button("Tạo chủ đề") and name.strip():
                create_deck(session, user["id"], name, language)
                rerun()

        deck = deck_selector(session, user["id"], key="manage_deck_id", label="Chủ đề cần quản lý")
        if deck is None:
            return

        allowed_langs = get_allowed_languages(user["name"])
        try:
            default_index = allowed_langs.index(deck.language)
        except ValueError:
            default_index = 0
        new_language = st.selectbox("Ngôn ngữ", allowed_langs, index=default_index)
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


def render_markdown_toolbar(content_key: str):
    st.caption("Chèn nhanh cú pháp Markdown:")
    cols = st.columns(4)
    tags = [
        ("Tiêu đề 1", "# "),
        ("Tiêu đề 2", "## "),
        ("In đậm", "**chữ in đậm**"),
        ("In nghiêng", "*chữ in nghiêng*"),
        ("Highlight", "<mark>nội dung nổi bật</mark>"),
        ("Danh sách", "\n- Mục 1\n- Mục 2\n"),
        ("Bảng", "\n| Cột 1 | Cột 2 |\n|---|---|\n| Ô 1 | Ô 2 |\n"),
        ("Hộp lưu ý", "\n> [!NOTE]\n> Nội dung lưu ý ở đây\n"),
    ]
    for index, (label, snippet) in enumerate(tags):
        col_idx = index % 4
        if cols[col_idx].button(label, key=f"btn_tag_{content_key}_{index}", use_container_width=True):
            current_val = st.session_state.get(content_key, "")
            st.session_state[content_key] = current_val + snippet
            st.rerun()


def grammar_notes_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("📚 Ghi chú ngữ pháp")

    if st.session_state.get("note_success_msg"):
        st.success(st.session_state.note_success_msg)
        st.session_state.pop("note_success_msg", None)

    tab_new, tab_search = st.tabs(["📝 Ghi chú mới", "🔍 Tìm kiếm ghi chú"])

    with SessionLocal() as session:
        # --- TAB 1: NEW NOTE ---
        with tab_new:
            st.subheader("Tạo ghi chú ngữ pháp mới")
            
            if "note_uploader_key" not in st.session_state:
                st.session_state.note_uploader_key = 0

            def on_mode_change():
                st.session_state.pop("new_note_title", None)
                st.session_state.pop("new_note_content", None)
                st.session_state.pop("new_note_preview_title", None)
                st.session_state.pop("new_note_preview_content", None)
                st.session_state.pop("pasted_note_image_base64", None)
                st.session_state.note_uploader_key += 1

            mode = st.radio(
                "Cách thêm ghi chú",
                ["Quét từ ảnh chụp", "Tự nhập tay"],
                horizontal=True,
                key="note_input_mode",
                on_change=on_mode_change
            )

            # Helper states
            if "new_note_title" not in st.session_state:
                st.session_state.new_note_title = ""
            if "new_note_content" not in st.session_state:
                st.session_state.new_note_content = ""

            if mode == "Quét từ ảnh chụp":
                # Clipboard paste handling for notes
                if st.session_state.get("clear_pasted_note"):
                    st.session_state.pop("pasted_note_image_base64", None)
                    st.session_state.clear_pasted_note = False

                st.markdown(
                    """
                    <style>
                    .st-key-pasted_note_image_base64 {
                        display: none !important;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )
                pasted_note_base64 = st.text_area("Pasted Note Base64", key="pasted_note_image_base64")

                col_u, col_p = st.columns(2, vertical_alignment="bottom")
                with col_u:
                    uploaded_note_img = st.file_uploader("Tải ảnh ghi chú lên", type=["jpg", "jpeg", "png", "webp"], key=f"upload_note_img_{st.session_state.note_uploader_key}")
                with col_p:
                    st.components.v1.html(
                        """
                        <style>
                            html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; }
                        </style>
                        <div id="paste-zone-note" tabindex="0" style="
                            border: 2px dashed rgba(128, 128, 128, 0.4);
                            border-radius: 8px;
                            padding: 16px 12px;
                            text-align: center;
                            color: var(--text-color, #2D2A26);
                            background-color: var(--secondary-background-color, rgba(128, 128, 128, 0.1));
                            cursor: pointer;
                            font-family: sans-serif;
                            font-size: 14px;
                            font-weight: 500;
                            outline: none;
                            transition: border-color 0.2s;
                            height: 100%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            box-sizing: border-box;
                        ">
                            📋 Bấm vào đây & nhấn Ctrl + V để dán ảnh ghi chú
                        </div>
                        <script>
                            const zone = document.getElementById('paste-zone-note');
                            try {
                                const parentStyle = window.parent.getComputedStyle(window.parent.document.documentElement);
                                zone.style.color = parentStyle.getPropertyValue('--text-color');
                                zone.style.backgroundColor = parentStyle.getPropertyValue('--secondary-background-color');
                                zone.addEventListener('focus', () => { zone.style.borderColor = parentStyle.getPropertyValue('--primary-color'); });
                                zone.addEventListener('blur', () => { zone.style.borderColor = 'rgba(128, 128, 128, 0.4)'; });
                            } catch (e) { console.error(e); }

                            const handlePaste = (e) => {
                                console.log("Note paste event triggered on element", e.currentTarget, e);
                                const items = (e.clipboardData || e.originalEvent.clipboardData).items;
                                for (let i = 0; i < items.length; i++) {
                                    if (items[i].type.indexOf('image') !== -1) {
                                        const blob = items[i].getAsFile();
                                        const reader = new FileReader();
                                        reader.onload = (event) => {
                                            const base64Data = event.target.result;
                                            const textarea = window.parent.document.querySelector('.st-key-pasted_note_image_base64 textarea');
                                            if (textarea) {
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

                            // Listen globally on the parent window's document to catch Ctrl+V anywhere
                            try {
                                if (window.parent && window.parent.document) {
                                    // Remove any previous note or vocab paste handlers
                                    if (window.parent.__rin_anki_paste_handler__) {
                                        window.parent.document.removeEventListener('paste', window.parent.__rin_anki_paste_handler__);
                                    }
                                    if (window.parent.__rin_anki_vocab_paste_handler__) {
                                        window.parent.document.removeEventListener('paste', window.parent.__rin_anki_vocab_paste_handler__);
                                    }
                                    if (window.parent.__rin_anki_note_paste_handler__) {
                                        window.parent.document.removeEventListener('paste', window.parent.__rin_anki_note_paste_handler__);
                                    }
                                    
                                    // Register current handler
                                    window.parent.__rin_anki_note_paste_handler__ = handlePaste;
                                    window.parent.document.addEventListener('paste', handlePaste);
                                    console.log("New global note paste listener registered on parent document.");
                                }
                            } catch (err) {
                                console.error("Global paste listener attachment failed:", err);
                            }
                        </script>
                        """,
                        height=75,
                    )

                note_image = None
                if uploaded_note_img is not None:
                    note_image = Image.open(uploaded_note_img)
                elif pasted_note_base64:
                    try:
                        import base64
                        from io import BytesIO
                        img_data = base64.b64decode(pasted_note_base64.split(",")[1])
                        note_image = Image.open(BytesIO(img_data))
                    except Exception as e:
                        st.error(f"Lỗi đọc ảnh từ clipboard: {e}")

                if note_image is not None:
                    st.image(note_image, width=420)
                    if pasted_note_base64:
                        if st.button("Xóa ảnh đã dán", key="clear_pasted_note_btn", use_container_width=True):
                            st.session_state.clear_pasted_note = True
                            st.rerun()

                    if st.button("Quét và trích xuất bằng AI", use_container_width=True):
                        with st.spinner("AI đang quét chữ viết tay và phân tích điểm ngữ pháp..."):
                            optimized = optimize_image(note_image)
                            extracted_markdown = GrammarAgent().process_note_with_vocab(optimized, session, user["id"])
                            # Parse title from the first line if it starts with #
                            lines = extracted_markdown.strip().split("\n")
                            title_found = False
                            if lines and lines[0].strip().startswith("#"):
                                first_line = lines[0].strip()
                                parsed_title = first_line.lstrip("#").strip()
                                if parsed_title:
                                    import re
                                    cleaned_title = re.sub(r'^(ngữ\s+pháp\s*)', '', parsed_title, flags=re.IGNORECASE).strip()
                                    st.session_state.new_note_title = cleaned_title
                                    st.session_state.new_note_content = "\n".join(lines[1:]).strip()
                                    title_found = True
                            
                            if not title_found:
                                st.session_state.new_note_content = extracted_markdown
                                now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
                                st.session_state.new_note_title = f"Ghi chú {now_str}"
                            st.session_state.new_note_preview_title = st.session_state.new_note_title
                            st.session_state.new_note_preview_content = st.session_state.new_note_content
                            st.rerun()

            elif mode == "Tự nhập tay":
                if st.button("Khởi tạo khung soạn thảo mới", use_container_width=True):
                    st.session_state.new_note_content = "# Soạn thảo ghi chú mới tại đây\n"
                    st.session_state.new_note_title = "Ghi chú mới"
                    st.session_state.new_note_preview_title = st.session_state.new_note_title
                    st.session_state.new_note_preview_content = st.session_state.new_note_content
                    st.rerun()

            # Side-by-side Editor & Preview for New Note
            if st.session_state.new_note_content:
                st.write("---")
                st.subheader("Khung soạn thảo & Xem trước")
                
                col_ed, col_prev = st.columns(2, gap="large")
                with col_ed:
                    st.text_input("Tiêu đề ghi chú", key="new_note_title")
                    render_markdown_toolbar("new_note_content")
                    st.text_area("Nội dung (Markdown)", key="new_note_content", height=450)
                
                with col_prev:
                    col_p_title, col_p_btn = st.columns([2, 1], vertical_alignment="center")
                    with col_p_title:
                        st.caption("Bản xem trước (Xem trước thủ công):")
                    with col_p_btn:
                        if st.button("Cập nhật xem trước", key="update_new_preview", use_container_width=True):
                            st.session_state.new_note_preview_title = st.session_state.new_note_title
                            st.session_state.new_note_preview_content = st.session_state.new_note_content
                            st.rerun()
                    with st.container(border=True):
                        title_val = st.session_state.get("new_note_preview_title", "")
                        content_val = st.session_state.get("new_note_preview_content", "")
                        if not title_val and not content_val:
                            st.info("Nhấn 'Cập nhật xem trước' để hiển thị bản xem trước.")
                        else:
                            st.markdown(f"## {title_val}", unsafe_allow_html=True)
                            st.markdown("---")
                            st.markdown(content_val, unsafe_allow_html=True)
                
                left_btn, right_btn = st.columns(2)
                if left_btn.button("Lưu ghi chú", use_container_width=True):
                    if not st.session_state.new_note_title.strip():
                        st.warning("Vui lòng điền tiêu đề ghi chú.")
                    else:
                        new_note = create_grammar_note(session, user["id"], st.session_state.new_note_title, st.session_state.new_note_content)
                        # Auto-tag the note based on its title
                        GrammarAgent().auto_tag_note(session, user["id"], new_note.id, new_note.title)
                        st.session_state.note_success_msg = "Đã lưu ghi chú thành công!"
                        # Reset states
                        st.session_state.pop("new_note_title", None)
                        st.session_state.pop("new_note_content", None)
                        st.session_state.pop("new_note_preview_title", None)
                        st.session_state.pop("new_note_preview_content", None)
                        st.session_state.pop("pasted_note_image_base64", None)
                        st.session_state.note_uploader_key += 1
                        st.rerun()
                if right_btn.button("Hủy bỏ", use_container_width=True):
                    st.session_state.pop("new_note_title", None)
                    st.session_state.pop("new_note_content", None)
                    st.session_state.pop("new_note_preview_title", None)
                    st.session_state.pop("new_note_preview_content", None)
                    st.session_state.pop("pasted_note_image_base64", None)
                    st.session_state.note_uploader_key += 1
                    st.rerun()

        # --- TAB 2: SEARCH NOTES ---
        with tab_search:
            st.subheader("Tìm kiếm và Tra cứu ghi chú")
            
            col_menu, col_content = st.columns([1, 3], gap="large")
            
            with col_menu:
                search_query = st.text_input("Tìm kiếm", placeholder="Tìm tiêu đề hoặc nội dung...", label_visibility="collapsed")
                # Fetch existing tags for the current user
                all_tags = [t.name for t in get_user_tags(session, user["id"])]
                selected_tags = st.multiselect("Lọc theo thẻ (Tags)", options=all_tags, placeholder="Chọn thẻ để lọc...")
                
                notes = get_grammar_notes(session, user["id"], search_query)
                if selected_tags:
                    notes = [n for n in notes if all(any(t.name == stag for t in n.tags) for stag in selected_tags)]
                
                selected_note = None
                if not notes:
                    st.info("Không tìm thấy ghi chú nào.")
                else:
                    # Determine currently selected note
                    current_selected_id = st.session_state.get("selected_note_id")
                    matching_ids = [n.id for n in notes]
                    if current_selected_id not in matching_ids:
                        current_selected_id = notes[0].id
                        st.session_state.selected_note_id = current_selected_id
                    
                    selected_note = next((n for n in notes if n.id == current_selected_id), None)
                    
                    with st.container(height=500):
                        for note in notes:
                            btn_type = "primary" if note.id == current_selected_id else "secondary"
                            if st.button(f"📓 {note.title}", key=f"menu_note_{note.id}", use_container_width=True, type=btn_type):
                                st.session_state.selected_note_id = note.id
                                st.rerun()
                            # Render small tag pills below the button
                            if note.tags:
                                tag_html = " ".join([
                                    f'<span style="background-color: rgba(13, 148, 136, 0.1); color: var(--primary-color, #0D9488); border: 1px solid rgba(13, 148, 136, 0.2); padding: 1px 6px; border-radius: 12px; font-size: 10px; margin-right: 4px; display: inline-block; font-weight: 500;">#{t.name}</span>'
                                    for t in note.tags
                                ])
                                st.markdown(f'<div style="margin-top: -6px; margin-bottom: 8px; padding-left: 8px;">{tag_html}</div>', unsafe_allow_html=True)

                    # Reordering controls
                    if selected_note:
                        st.write("---")
                        st.caption("Thứ tự hiển thị:")
                        col_up, col_down = st.columns(2)
                        
                        notes_list = list(notes)
                        try:
                            idx = next(i for i, n in enumerate(notes_list) if n.id == selected_note.id)
                            can_up = idx > 0
                            can_down = idx < len(notes_list) - 1
                        except StopIteration:
                            can_up = False
                            can_down = False
                            
                        if col_up.button("⬆️ Lên", disabled=not can_up, use_container_width=True):
                            reorder_grammar_note(session, selected_note.id, "up")
                            rerun()
                        if col_down.button("⬇️ Xuống", disabled=not can_down, use_container_width=True):
                            reorder_grammar_note(session, selected_note.id, "down")
                            rerun()

                    # Batch auto-tagger control
                    st.write("---")
                    if st.button("🤖 Tự động gắn thẻ thư viện", key="batch_auto_tag_btn", use_container_width=True, help="Quét toàn bộ ghi chú cũ chưa có thẻ và tự động gán thẻ bằng AI"):
                        all_user_notes = get_grammar_notes(session, user["id"])
                        notes_to_tag = [n for n in all_user_notes if not n.tags]
                        if not notes_to_tag:
                            st.info("Tất cả ghi chú đều đã được gắn thẻ!")
                        else:
                            progress_bar = st.progress(0.0)
                            status_text = st.empty()
                            total = len(notes_to_tag)
                            agent = GrammarAgent()
                            count = 0
                            for i, note in enumerate(notes_to_tag):
                                status_text.text(f"Đang gắn thẻ: {note.title} ({i+1}/{total})...")
                                agent.auto_tag_note(session, user["id"], note.id, note.title)
                                count += 1
                                progress_bar.progress(float(i + 1) / total)
                            progress_bar.empty()
                            status_text.empty()
                            st.success(f"Đã tự động gắn thẻ thành công cho {count} ghi chú!")
                            st.rerun()
            
            with col_content:
                if selected_note is not None:
                    # Check if in edit mode for this note
                    if st.session_state.get("edit_note_id") == selected_note.id:
                        # Edit mode
                        st.subheader(f"Đang sửa ghi chú: {selected_note.title}")
                        
                        col_edit_l, col_edit_r = st.columns(2, gap="medium")
                        with col_edit_l:
                            st.text_input("Tiêu đề", key="edit_note_title")
                            render_markdown_toolbar("edit_note_content")
                            st.text_area("Nội dung (Markdown)", key="edit_note_content", height=450)
                        with col_edit_r:
                            col_p_title, col_p_btn = st.columns([2, 1], vertical_alignment="center")
                            with col_p_title:
                                st.caption("Bản xem trước (Xem trước thủ công):")
                            with col_p_btn:
                                if st.button("Cập nhật xem trước", key="update_edit_preview", use_container_width=True):
                                    st.session_state.edit_note_preview_title = st.session_state.edit_note_title
                                    st.session_state.edit_note_preview_content = st.session_state.edit_note_content
                                    st.rerun()
                            with st.container(border=True):
                                title_val = st.session_state.get("edit_note_preview_title", "")
                                content_val = st.session_state.get("edit_note_preview_content", "")
                                if not title_val and not content_val:
                                    st.info("Nhấn 'Cập nhật xem trước' để hiển thị bản xem trước.")
                                else:
                                    st.markdown(f"## {title_val}", unsafe_allow_html=True)
                                    st.markdown("---")
                                    st.markdown(content_val, unsafe_allow_html=True)
                        
                        btn_save, btn_cancel = st.columns(2)
                        if btn_save.button("Lưu thay đổi", key="save_edit_note_btn", use_container_width=True):
                            if not st.session_state.edit_note_title.strip():
                                st.warning("Vui lòng nhập tiêu đề.")
                            else:
                                update_grammar_note(session, selected_note.id, st.session_state.edit_note_title, st.session_state.edit_note_content)
                                # Auto-tag the note based on its title
                                GrammarAgent().auto_tag_note(session, user["id"], selected_note.id, st.session_state.edit_note_title)
                                st.success("Đã cập nhật thay đổi thành công!")
                                st.session_state.pop("edit_note_id", None)
                                st.session_state.pop("edit_note_preview_title", None)
                                st.session_state.pop("edit_note_preview_content", None)
                                st.rerun()
                        if btn_cancel.button("Hủy sửa", key="cancel_edit_note_btn", use_container_width=True):
                            st.session_state.pop("edit_note_id", None)
                            st.session_state.pop("edit_note_preview_title", None)
                            st.session_state.pop("edit_note_preview_content", None)
                            st.rerun()
                    else:
                        # View mode
                        with st.container(border=True):
                            st.markdown(f"## {selected_note.title}", unsafe_allow_html=True)
                            col_meta_l, col_meta_r = st.columns([1, 1])
                            with col_meta_l:
                                st.caption(f"Ngày lưu: {selected_note.created_at.strftime('%d/%m/%Y %H:%M:%S')}")
                            with col_meta_r:
                                if selected_note.tags:
                                    tag_html = " ".join([
                                        f'<span style="background-color: rgba(13, 148, 136, 0.1); color: var(--primary-color, #0D9488); border: 1px solid rgba(13, 148, 136, 0.2); padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-right: 6px; display: inline-block; font-weight: 500;">#{t.name}</span>'
                                        for t in selected_note.tags
                                    ])
                                    st.markdown(f'<div style="text-align: right; margin-top: -4px;">{tag_html}</div>', unsafe_allow_html=True)
                            st.markdown("---")
                            st.markdown(selected_note.content, unsafe_allow_html=True)

                        col_actions = st.columns([1, 1, 4])
                        if col_actions[0].button("Sửa ghi chú", use_container_width=True):
                            st.session_state.edit_note_id = selected_note.id
                            st.session_state.edit_note_title = selected_note.title
                            st.session_state.edit_note_content = selected_note.content
                            st.session_state.edit_note_preview_title = selected_note.title
                            st.session_state.edit_note_preview_content = selected_note.content
                            st.rerun()
                        if col_actions[1].button("Xóa ghi chú", use_container_width=True):
                            delete_grammar_note(session, selected_note.id)
                            st.success("Đã xóa ghi chú thành công!")
                            st.rerun()


def quiz_screen() -> None:
    user = current_user()
    assert user is not None
    st.title("Quiz")

    # Check if a quiz session is active
    quiz = st.session_state.get("quiz")
    is_active = quiz and "cards" in quiz and quiz["index"] < len(quiz["cards"])

    if not is_active:
        # If quiz is finished, show completion screen
        if quiz and quiz.get("cards") and quiz["index"] >= len(quiz["cards"]):
            # Save results to DB if not saved yet
            if not quiz.get("saved"):
                with st.spinner("Đang lưu kết quả quiz..."):
                    with SessionLocal() as session:
                        save_quiz_results(session, quiz.get("results", []))
                quiz["saved"] = True
            
            # Calculate mark
            results = quiz.get("results", [])
            total = len(quiz["cards"])
            remembered_cnt = sum(1 for r in results if r["result"] == "remembered")
            partial_cnt = sum(1 for r in results if r["result"] == "partial")
            forgot_cnt = sum(1 for r in results if r["result"] == "forgot")
            
            score = (remembered_cnt * 10 + partial_cnt * 5) / total if total > 0 else 0
            
            st.balloons()
            
            st.markdown(
                f"""
                <div style='border:1px solid rgba(128, 128, 128, 0.2); border-radius:8px; padding:24px; text-align:center; background-color: var(--secondary-background-color); margin-bottom: 24px;'>
                    <h2 style='color: var(--primary-color); margin-bottom: 8px;'>🎉 Hoàn thành lượt quiz!</h2>
                    <div style='font-size:48px; font-weight:700; color: var(--text-color);'>{score:.1f} <span style='font-size:24px; font-weight:normal;'>/ 10</span></div>
                    <div style='margin-top:12px; font-size:16px; color: var(--text-color); opacity: 0.8;'>
                        😄 Đã nhớ: <b>{remembered_cnt}</b> | 🤔 Nhớ sơ sơ: <b>{partial_cnt}</b> | 😵 Chưa nhớ: <b>{forgot_cnt}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            # Show review list
            review_list = [r for r in results if r["result"] in ("forgot", "partial")]
            if review_list:
                st.markdown("### 🔍 Danh sách từ cần ôn lại")
                
                # Prepare list data
                review_data = []
                for item in review_list:
                    card = item["card"]
                    side_str = "VN ➔ KR" if card["reversed"] else f"{quiz['deck_language']} ➔ VN"
                    status_str = "😵 Chưa nhớ" if item["result"] == "forgot" else "🤔 Nhớ sơ sơ"
                    
                    review_data.append({
                        "Từ": card["word"],
                        "Nghĩa": card["meaning"],
                        "Chiều ôn": side_str,
                        "Trạng thái": status_str,
                        "Ví dụ": card["example"],
                        "Ghi chú": card["note"]
                    })
                
                display_custom_table(pd.DataFrame(review_data), localize=False)
            else:
                st.success("Tuyệt vời! Bạn đã thuộc tất cả các từ trong lượt quiz này! 🥳")

            if st.button("Xóa lượt quiz & Quay lại", use_container_width=True):
                st.session_state.pop("quiz", None)
                st.session_state.pop("quiz_eval", None)
                st.rerun()
            return

        # Otherwise, show configuration UI (needs session)
        with SessionLocal() as session:
            deck = deck_selector(session, user["id"], key="quiz_deck_id", label="Chủ đề")
            if deck is None:
                return

            allowed_langs = ["KR", "EN", "JP", "CN"]
            is_allowed_lang = deck.language in allowed_langs

            # Show input requirement option if deck language is supported
            use_input = False
            if is_allowed_lang:
                use_input = st.checkbox("Yêu cầu nhập câu trả lời (Gõ bàn phím)", value=True, key="quiz_use_input")

            question_count = st.number_input("Số câu hỏi", min_value=1, max_value=100, value=20)
            if st.button("Bắt đầu quiz"):
                with st.spinner("Đang tải danh sách câu hỏi..."):
                    cards = due_vocabulary_cards(session, deck.id, int(question_count))
                if not cards:
                    st.info("Hiện chưa có thẻ nào đến hạn ôn.")
                else:
                    st.session_state.quiz = {
                        "deck_language": deck.language,
                        "use_input": use_input,
                        "cards": cards,
                        "index": 0,
                        "show_answer": False,
                        "results": [],
                        "saved": False,
                    }
                    st.session_state.pop("quiz_eval", None)
                    rerun()
        return

    # Active quiz UI
    card = quiz["cards"][quiz["index"]]
    
    # Reverse direction logic
    if card["reversed"]:
        front_text = card["meaning"]
        caption = f"Dịch sang {quiz['deck_language']}"
        back_text = card["word"]
    else:
        front_text = card["word"]
        caption = quiz['deck_language']
        back_text = card["meaning"]

    col_header, col_cancel = st.columns([6, 1])
    with col_header:
        st.caption(f"Câu {quiz['index'] + 1} / {len(quiz['cards'])}")
    with col_cancel:
        if st.button("Hủy quiz", use_container_width=True):
            if quiz.get("results") and not quiz.get("saved"):
                with st.spinner("Đang lưu tiến trình..."):
                    with SessionLocal() as session:
                        save_quiz_results(session, quiz["results"])
                quiz["saved"] = True
            st.session_state.pop("quiz", None)
            st.session_state.pop("quiz_eval", None)
            rerun()

    st.markdown(
        f"""
        <div style='border:1px solid rgba(128, 128, 128, 0.2); border-radius:8px; padding:32px; text-align:center; background-color: var(--secondary-background-color);'>
            <div style='font-size:48px; font-weight:700; color: var(--text-color);'>{front_text}</div>
            <div style='margin-top:8px; color: var(--text-color); opacity: 0.7;'>{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    is_keyboard_quiz = card["reversed"] and quiz.get("use_input")

    if is_keyboard_quiz:
        # Type answer quiz
        if not quiz["show_answer"]:
            with st.form("quiz_answer_form", clear_on_submit=True):
                user_ans = st.text_input("Nhập câu trả lời của bạn:")
                btn_check = st.form_submit_button("Kiểm tra đáp án")
            
            # Option to show answer without typing
            if st.button("Hiện đáp án trực tiếp", use_container_width=True):
                quiz["show_answer"] = True
                st.session_state.quiz_eval = None
                rerun()
            
            if btn_check:
                ans_clean = user_ans.strip()
                if not ans_clean:
                    st.warning("Vui lòng nhập câu trả lời trước khi kiểm tra.")
                else:
                    is_correct = False
                    matched_info = ""
                    
                    if ans_clean.lower() == back_text.strip().lower():
                        is_correct = True
                    elif quiz["deck_language"] == "KR":
                        # For Korean, also check if it matches conjugation forms
                        conj = card.get("conjugation_data", {})
                        for k, val in conj.items():
                            if val and ans_clean == val.strip():
                                is_correct = True
                                label = {"a_eo_yeo": "아/어/여", "eun_neun": "은/는", "eu_ni_kka": "(으)니까"}.get(k, k)
                                matched_info = f" (Khớp với dạng chia {label}: {val})"
                                break
                    
                    st.session_state.quiz_eval = {
                        "is_correct": is_correct,
                        "user_ans": ans_clean,
                        "matched_info": matched_info,
                    }
                    quiz["show_answer"] = True
                    rerun()
            return

        else:
            # Answer phase showing evaluation
            eval_data = st.session_state.get("quiz_eval")
            if eval_data is not None:
                if eval_data["is_correct"]:
                    st.success(f"🎉 **Đúng rồi!** Bạn nhập: `{eval_data['user_ans']}`{eval_data['matched_info']}")
                else:
                    st.error(f"❌ **Chưa chính xác.** Bạn nhập: `{eval_data['user_ans']}`. Đáp án đúng phải là: `{back_text}`")
            else:
                st.info(f"Đáp án đúng: `{back_text}`")
    else:
        # Standard flashcard quiz
        if not quiz["show_answer"]:
            if st.button("Hiện đáp án", use_container_width=True):
                quiz["show_answer"] = True
                rerun()
            return

    # Back of card (Answer details)
    if not is_keyboard_quiz or st.session_state.get("quiz_eval") is None:
        st.markdown(f"### {back_text}")
    
    if card["note"]:
        st.info(card["note"])
    if card["example"]:
        st.write(card["example"])

    # Display conjugation columns if it's a Korean card in Korean deck
    if quiz["deck_language"] == "KR":
        conj = card.get("conjugation_data", {})
        if conj.get("a_eo_yeo") or conj.get("eun_neun") or conj.get("eu_ni_kka"):
            st.write("---")
            st.caption("Các dạng chia động từ (Hàn):")
            c1, c2, c3 = st.columns(3)
            c1.metric("아/어/여", conj.get("a_eo_yeo") or "—")
            c2.metric("은/는", conj.get("eun_neun") or "—")
            c3.metric("(으)니까", conj.get("eu_ni_kka") or "—")

    left, middle, right = st.columns(3)
    actions = [
        (left, "😵 Chưa nhớ", "forgot"),
        (middle, "🤔 Nhớ sơ sơ", "partial"),
        (right, "😄 Nhớ rồi", "remembered"),
    ]
    for column, label, result in actions:
        if column.button(label, use_container_width=True):
            if "results" not in quiz:
                quiz["results"] = []
            quiz["results"].append({
                "card": card,
                "result": result
            })
            quiz["index"] += 1
            quiz["show_answer"] = False
            st.session_state.pop("quiz_eval", None)
            rerun()

    # Keyboard listener for rating hotkeys 1, 2, 3
    st.components.v1.html(
        """
        <script>
            const handleKeyDown = (e) => {
                const activeEl = window.parent.document.activeElement;
                if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable)) {
                    return;
                }
                
                const h1s = Array.from(window.parent.document.querySelectorAll('h1'));
                const isQuizPage = h1s.some(h1 => h1.innerText && h1.innerText.trim() === "Quiz");
                if (!isQuizPage) {
                    return;
                }
                
                if (e.key === '1' || e.key === '2' || e.key === '3') {
                    const buttons = Array.from(window.parent.document.querySelectorAll('button'));
                    let targetText = "";
                    if (e.key === '1') targetText = "Chưa nhớ";
                    else if (e.key === '2') targetText = "Nhớ sơ sơ";
                    else if (e.key === '3') targetText = "Nhớ rồi";
                    
                    const targetBtn = buttons.find(btn => btn.innerText && btn.innerText.includes(targetText));
                    if (targetBtn) {
                        targetBtn.click();
                        e.preventDefault();
                    }
                }
            };

            try {
                if (window.parent) {
                    if (window.parent.__quiz_keydown_handler__) {
                        window.parent.removeEventListener('keydown', window.parent.__quiz_keydown_handler__, true);
                    }
                    window.parent.__quiz_keydown_handler__ = handleKeyDown;
                    window.parent.addEventListener('keydown', handleKeyDown, true);
                    console.log("Registered global quiz hotkeys (1, 2, 3).");
                }
            } catch (err) {
                console.error("Failed to attach quiz keydown listener:", err);
            }
        </script>
        """,
        height=0,
    )



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
        with st.expander("🤖 4. Tự Động Chia Động Từ Tiếng Hàn (AI)"):
            st.markdown(
                """
                Dành riêng cho chủ đề tiếng Hàn (**KR**):
                * Trong tab **Danh sách từ**, nhấn nút **Tự động chia động từ (AI)**.
                * Hệ thống tự động lọc các từ kết thúc bằng **"다"** (động từ/tính từ) chưa được chia để gửi yêu cầu đến Gemini (giúp tiết kiệm API cost tối đa).
                * Kết quả tự động phân tích và tạo thêm 3 cột: **아/어/여**, **은/n는** (định ngữ), và **(으)니까**.
                * Bạn có thể bấm chọn **Ghi đè từ đã chia** nếu muốn chia lại hàng loạt. Các cột này cũng hiển thị trong form chỉnh sửa từ.
                """
            )
        with st.expander("📓 5. Quản Lý Ghi Chú Ngữ Pháp (AI)"):
            st.markdown(
                """
                Lưu trữ và ôn tập cấu trúc ngữ pháp thông minh:
                * **Tạo ghi chú mới**:
                  * Quét từ hình ảnh ghi chú viết tay bằng AI (tự động nhận dạng và dùng thẻ `<mark>` highlight các công thức ngữ pháp cốt lõi) hoặc tự nhập tay.
                  * Soạn thảo với **Markdown Editor & Live Preview** side-by-side hiển thị trực quan thay đổi.
                  * Sử dụng thanh công cụ phím bấm chèn nhanh định dạng Markdown (Tiêu đề, in đậm, in nghiêng, highlight, danh sách, bảng biểu, hộp ghi chú).
                * **Tìm kiếm ghi chú**:
                  * Tra cứu ghi chú nhanh chóng theo tiêu đề hoặc nội dung ngữ pháp.
                  * Đọc ghi chú với định dạng Markdown chuyên nghiệp. Hỗ trợ đầy đủ chức năng sửa đổi nội dung hoặc xóa ghi chú.
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
        
        with st.expander("⌨️ Nhập Câu Trả Lời Khi Làm Quiz"):
            st.markdown(
                """
                Ôn tập chủ động bằng cách gõ bàn phím:
                * Khi bắt đầu Quiz với chủ đề tiếng Hàn (KR), Anh (EN), Nhật (JP), hay Trung (CN), bạn có thể tích chọn **Yêu cầu nhập câu trả lời (Gõ bàn phím)**.
                * Hệ thống hiển thị ô nhập liệu để bạn viết đáp án ngoại ngữ.
                * **So khớp thông minh**: Kết quả gõ của bạn được so sánh với từ gốc. Đặc biệt với tiếng Hàn, hệ thống sẽ kiểm tra xem câu trả lời của bạn có khớp với bất kỳ dạng chia động từ nào đã lưu trong database (**아/어/여**, **은/n는**, **(으)니까**) hay không để công nhận đáp án chính xác!
                """
            )
            
        st.info(
            """
            **Chu kỳ ôn tập:**
            1. **😵 Chưa nhớ**: Xem lại sau **5 phút**.
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
        # Reset the grammar note states on menu tab switch
        st.session_state.pop("new_note_title", None)
        st.session_state.pop("new_note_content", None)
        st.session_state.pop("new_note_preview_title", None)
        st.session_state.pop("new_note_preview_content", None)
        st.session_state.pop("pasted_note_image_base64", None)
        if "note_uploader_key" in st.session_state:
            st.session_state.note_uploader_key += 1
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
    else:
        page = render_top_bar()
        if page == "Thêm từ vựng":
            add_vocabulary_screen()
        elif page == "Danh sách từ":
            word_list_screen()
        elif page == "Chủ đề":
            topic_screen()
        elif page == "Ghi chú ngữ pháp":
            grammar_notes_screen()
        elif page == "Quiz":
            quiz_screen()
        else:
            hdsd_screen()

    # Footer version number
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: var(--text-color); opacity: 0.5; font-size: 0.8rem; margin-top: 24px; margin-bottom: 8px;'>"
        "Rin Anki v20260705 • Phát triển bởi Rin"
        "</div>",
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
