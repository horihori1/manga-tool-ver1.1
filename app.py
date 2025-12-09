import streamlit as st
import os
import concurrent.futures
import io
from PIL import Image

# Google Gen AI SDK
# 実行前に pip install google-genai streamlit を忘れずに
from google import genai
from google.genai import types

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="MangaMaker AI", page_icon="🎨")

# --- CSS設定 (UIデザイン) ---
st.markdown("""
<style>
    /* ボタンデザイン */
    .stButton>button {
        width: 100%;
        background: linear-gradient(45deg, #ec4899, #8b5cf6);
        color: white;
        height: 3.5em;
        font-weight: bold;
        border: none;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 8px rgba(0,0,0,0.2);
        color: white;
    }
    /* サイドバー背景 */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
    }
    /* タイトルグラデーション */
    .main-header {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #ec4899, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# --- APIキー取得関数 ---
def get_api_key():
    # 1. 環境変数
    key = os.environ.get("GOOGLE_API_KEY")
    # 2. Streamlit Secrets
    if not key:
        try:
            key = st.secrets["GOOGLE_API_KEY"]
        except FileNotFoundError:
            pass
    return key

# --- 画像生成関数（エラーハンドリング強化版） ---
def generate_single_image(client, prompt, character_parts, pose_bytes, model_name):
    """
    画像を生成する関数。
    成功すれば画像データ(bytes)を返し、失敗すればエラーメッセージ(str)を返す。
    """
    try:
        # GenerateContent APIの呼び出し
        response = client.models.generate_content(
            model=model_name,
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
                response_mime_type="image/png", # 画像出力を要求
            )
        )
        
        # レスポンスの解析
        if response.candidates:
            for part in response.candidates[0].content.parts:
                # 1. 画像データが含まれている場合（成功）
                if part.inline_data:
                    return part.inline_data.data
                
                # 2. テキストで返答された場合（生成拒否など）
                if part.text:
                    return f"⚠️ 生成失敗 (AIからの応答): {part.text}"
        
        return "⚠️ エラー: レスポンスにデータが含まれていません。"

    except Exception as e:
        # システムエラー（APIキー間違い、モデル名間違い、通信エラーなど）
        return f"🚫 システムエラー: {str(e)}"

def main():
    # --- サイドバー：設定パネル ---
    with st.sidebar:
        st.title("⚙️ 設定パネル")
        
        # 1. APIキー設定
        api_key = get_api_key()
        if not api_key:
            with st.expander("🔑 APIキー設定", expanded=True):
                api_key = st.text_input("Google API Keyを入力", type="password")
                if not api_key:
                    st.warning("APIキーを入力してください")
                    st.stop()
        
        # クライアント初期化
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            st.error(f"クライアント初期化エラー: {e}")
            st.stop()

        st.divider()

        # 2. 画像アップロード
        st.subheader("1. キャラクター画像")
        st.caption("キャラの特徴（顔、服装）がわかる画像をアップロード")
        char_files = st.file_uploader("キャラクター画像", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
        if char_files:
            st.image([Image.open(f) for f in char_files], width=80)

        st.subheader("2. ポーズ参照画像")
        st.caption("構図やポーズの元になる画像")
        pose_file = st.file_uploader("ポーズ画像", type=['png', 'jpg', 'jpeg', 'webp'])
        if pose_file:
            st.image(Image.open(pose_file), use_container_width=True)

        st.divider()

        # 3. パラメータ設定
        st.subheader("3. 詳細設定")
        custom_prompt = st.text_area("追加プロンプト", placeholder="例：少年漫画風、ドラマチックな影、高画質...", height=80)
        
        num_images = st.slider("生成枚数", 1, 10, 2) # デフォルト2枚
        
        # モデル選択（重要：動かない場合はここを変更する）
        model_name = st.selectbox(
            "使用モデル", 
            [
                "gemini-2.0-flash-exp",   # 最新の実験版（推奨）
                "gemini-1.5-pro",         # 安定版（画像生成できない場合あり）
                "imagen-3.0-generate-001" # 画像生成専用（権限が必要）
            ], 
            index=0,
            help="エラーが出る場合はモデルを変更してみてください。"
        )

        st.divider()
        generate_btn = st.button("✨ 画像を生成する")

    # --- メインエリア ---
    st.markdown('<h1 class="main-header">🎨 MangaMaker AI</h1>', unsafe_allow_html=True)
    st.markdown("キャラクター画像とポーズ画像を組み合わせて、漫画のコマを生成します。")

    # セッション状態の初期化
    if 'generated_images' not in st.session_state:
        st.session_state.generated_images = []

    # --- 生成処理 ---
    if generate_btn:
        if not char_files or not pose_file:
            st.error("⚠️ エラー: キャラクター画像とポーズ画像の両方をセットしてください。")
        else:
            status_area = st.container()
            with status_area:
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.info("🚀 準備中...")

            # データ変換
            character_parts = []
            for cf in char_files:
                character_parts.append(types.Part.from_bytes(data=cf.getvalue(), mime_type=cf.type))
            pose_bytes = pose_file.getvalue()

            # プロンプト作成
            prompt_text = f"""
            You are a professional manga artist. Generate an image based on inputs.
            
            [INPUTS]
            - Character Reference: Follow the visual style of attached character images closely.
            - Pose Reference: Use the last image for pose and composition.
            
            [OUTPUT]
            - High-quality manga illustration. 16:9 aspect ratio.
            - {custom_prompt if custom_prompt else "Standard Japanese manga style, clean lines."}
            """

            status_text.info(f"🎨 生成中... (モデル: {model_name}, 枚数: {num_images}枚)")
            
            results = []
            
            # 並列処理
            workers = min(num_images, 4)
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(generate_single_image, client, prompt_text, character_parts, pose_bytes, model_name) 
                    for _ in range(num_images)
                ]
                
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = future.result()
                    
                    # 結果の判定 logic
                    if isinstance(result, bytes):
                        # 画像データ(成功)
                        results.append(result)
                    elif isinstance(result, str):
                        # エラーメッセージ(失敗) - 画面に赤字で表示
                        st.error(result)
                    
                    progress_bar.progress((i + 1) / num_images)

            # 結果保存
            if results:
                st.session_state.generated_images = results
                status_text.success(f"✅ 完了: {len(results)}枚の画像を生成しました！")
            else:
                status_text.error("❌ 画像が1枚も生成されませんでした。上のエラーメッセージを確認してください。")
            
            progress_bar.empty()

    # --- 結果表示 ---
    st.divider()
    st.subheader("🖼️ 生成結果")

    if st.session_state.generated_images:
        cols = st.columns(2)
        for idx, img_bytes in enumerate(st.session_state.generated_images):
            with cols[idx % 2]:
                img = Image.open(io.BytesIO(img_bytes))
                st.image(img, use_container_width=True)
                
                st.download_button(
                    label=f"⬇️ 画像 #{idx+1} を保存",
                    data=img_bytes,
                    file_name=f"manga_{idx+1}.png",
                    mime="image/png",
                    key=f"dl_{idx}",
                    use_container_width=True
                )
    else:
        st.caption("ここに生成結果が表示されます。")

if __name__ == "__main__":
    main()
