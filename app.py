import streamlit as st
import os
from google import genai
from google.genai import types
import concurrent.futures
from PIL import Image
import io

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="MangaMaker AI", page_icon="🎨")

# --- CSS設定 ---
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        background-color: #ec4899;
        color: white;
        height: 3em;
        font-weight: bold;
        border: none;
        border-radius: 8px;
    }
    .stButton>button:hover {
        background-color: #db2777;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- APIキーとクライアントの初期化 ---
def get_api_key():
    # 1. 環境変数から取得
    key = os.environ.get("GOOGLE_API_KEY")
    # 2. Streamlit Secretsから取得
    if not key:
        try:
            key = st.secrets["GOOGLE_API_KEY"]
        except FileNotFoundError:
            pass
    return key

api_key = get_api_key()

# キーが見つからない場合はサイドバーで入力を促す
if not api_key:
    with st.sidebar:
        st.warning("API Key not found in environment or secrets.")
        api_key = st.text_input("Enter Google API Key", type="password")
        if not api_key:
            st.info("Please set your API key to proceed.")
            st.stop()

# クライアント初期化
try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"Failed to initialize Gemini client: {e}")
    st.stop()


def generate_single_image(prompt, character_parts, pose_bytes):
    """1枚の画像を生成する関数"""
    try:
        # モデル名は最新の有効なものを指定してください
        # 注意: 'gemini-2.5-flash-image' はプレビュー等の特定の状況でのみ有効な場合があります。
        # 一般公開されている画像生成モデルは 'imagen-3.0-generate-001' 等の場合があります。
        # ここでは元のコードのモデル名を維持します。
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', # 仮のモデル名（必要に応じて変更してください）
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_text(prompt),
                        *character_parts,
                        types.Part.from_bytes(data=pose_bytes, mime_type="image/png")
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="image/png", # 画像出力を明示
                # 画像生成専用モデルでない場合、ここでのaspect_ratio指定はエラーになる可能性があります
                # 汎用モデルの場合はプロンプトでサイズを指定するのが一般的です
            )
        )
        
        # レスポンスから画像データを抽出
        # モデルによってバイナリの返却形式が異なる場合があります
        if response.candidates:
            for part in response.candidates[0].content.parts:
                # バイナリデータが含まれている場合
                if part.inline_data:
                    return part.inline_data.data
                # 画像生成モデルがURIを返す場合など
                # (必要に応じて実装を追加)
        return None
    except Exception as e:
        print(f"Error generating image: {e}")
        return None

def main():
    st.title("🎨 MangaMaker AI")
    st.caption("Powered by Google Gemini / Imagen")

    if 'generated_images' not in st.session_state:
        st.session_state.generated_images = []

    col1, col2, col3 = st.columns([1, 1, 2])

    # --- Column 1: キャラクター設定 ---
    with col1:
        st.header("1. Characters")
        st.info("Upload character sheets (Front, Side, Expressions).")
        char_files = st.file_uploader("Character Images", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
        
        if char_files:
            st.image([Image.open(f) for f in char_files], width=100, caption=[f.name for f in char_files])
        
        custom_prompt = st.text_area("Style / Additional Prompt", placeholder="e.g., Shonen manga style, high contrast, dramatic shadows...", height=100)

    # --- Column 2: ポーズ設定 ---
    with col2:
        st.header("2. Pose")
        st.info("Upload a pose reference image.")
        pose_file = st.file_uploader("Pose Reference", type=['png', 'jpg', 'jpeg', 'webp'])
        
        if pose_file:
            st.image(Image.open(pose_file), use_container_width=True, caption="Pose Target")

        st.markdown("---")
        generate_btn = st.button("✨ Generate 10 Variations")

    # --- 生成ロジック ---
    if generate_btn:
        if not char_files or not pose_file:
            st.error("⚠️ Please upload both Character Sheets and a Pose Reference.")
        else:
            with col3:
                status_container = st.container()
                status_text = status_container.empty()
                progress_bar = status_container.progress(0)
                
                status_text.markdown("**🚀 Initializing...**")

                # 入力データの準備
                character_parts = []
                for cf in char_files:
                    bytes_data = cf.getvalue()
                    character_parts.append(types.Part.from_bytes(data=bytes_data, mime_type=cf.type))
                
                pose_bytes = pose_file.getvalue()

                # プロンプト作成
                prompt_text = f"""
                You are a manga artist. Generate an image based on these inputs:
                1. Character Reference: Use the attached character sheets for appearance.
                2. Pose Reference: The last image defines the pose.
                
                OUTPUT REQUIREMENT:
                - Create a high-quality manga illustration.
                - Aspect Ratio: 16:9.
                - {custom_prompt if custom_prompt else "Standard manga style."}
                """

                status_text.markdown("**🎨 Generating 10 variations in parallel...**")
                
                results = []
                # 並列処理
                # 注意: APIのRate Limit（クォータ制限）に引っかかる場合は max_workers を減らしてください (例: 2)
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [
                        executor.submit(generate_single_image, prompt_text, character_parts, pose_bytes) 
                        for _ in range(10) # 10枚生成
                    ]
                    
                    for i, future in enumerate(concurrent.futures.as_completed(futures)):
                        result = future.result()
                        if result:
                            results.append(result)
                        progress_bar.progress((i + 1) / 10)

                st.session_state.generated_images = results
                status_text.success(f"✅ Generated {len(results)} images!")
                progress_bar.empty()

    # --- Column 3: 結果表示 ---
    with col3:
        st.header("3. Results")
        
        if st.session_state.generated_images:
            res_cols = st.columns(2)
            for idx, img_bytes in enumerate(st.session_state.generated_images):
                with res_cols[idx % 2]:
                    image = Image.open(io.BytesIO(img_bytes))
                    st.image(image, use_container_width=True)
                    
                    st.download_button(
                        label=f"⬇️ Download #{idx+1}",
                        data=img_bytes,
                        file_name=f"manga_gen_{idx+1}.png",
                        mime="image/png",
                        key=f"dl_{idx}"
                    )
        else:
            st.info("Generated images will appear here.")

if __name__ == "__main__":
    main()
