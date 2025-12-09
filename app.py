import streamlit as st
import os
from google import genai
from google.genai import types
import concurrent.futures
from PIL import Image
import io

# --- ページ設定 ---
st.set_page_config(layout="wide", page_title="MangaMaker AI", page_icon="🎨")

# --- CSS設定 (UI調整) ---
st.markdown("""
<style>
    /* メインボタンのスタイル */
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
    /* サイドバーの微調整 */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
    }
    /* ヘッダーのスタイル */
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

# --- APIキー管理 ---
def get_api_key():
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        try:
            key = st.secrets["GOOGLE_API_KEY"]
        except FileNotFoundError:
            pass
    return key

# --- 画像生成関数 ---
def generate_single_image(client, prompt, character_parts, pose_bytes, model_name):
    """1枚の画像を生成する関数"""
    try:
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
                response_mime_type="image/png",
            )
        )
        
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    return part.inline_data.data
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    # --- サイドバー：設定エリア ---
    with st.sidebar:
        st.title("⚙️ 設定パネル")
        
        # 1. APIキー設定
        api_key = get_api_key()
        if not api_key:
            with st.expander("🔑 APIキー設定", expanded=True):
                api_key = st.text_input("Google API Keyを入力", type="password")
                if not api_key:
                    st.warning("APIキーを設定してください")
                    st.stop()
        
        # クライアント初期化
        try:
            client = genai.Client(api_key=api_key)
        except Exception as e:
            st.error(f"接続エラー: {e}")
            st.stop()

        st.divider()

        # 2. キャラクター画像
        st.subheader("1. キャラクター設定画")
        st.caption("キャラの特徴がわかる画像（正面、横顔、表情集など）をアップロードしてください。")
        char_files = st.file_uploader("キャラクター画像を選択", type=['png', 'jpg', 'jpeg', 'webp'], accept_multiple_files=True)
        
        # プレビュー
        if char_files:
            st.image([Image.open(f) for f in char_files], width=80, caption=[f.name[:10] for f in char_files])

        st.divider()

        # 3. ポーズ画像
        st.subheader("2. ポーズ指定")
        st.caption("構図やポーズの元となる画像を1枚アップロードしてください。")
        pose_file = st.file_uploader("ポーズ画像を選択", type=['png', 'jpg', 'jpeg', 'webp'])
        
        # プレビュー
        if pose_file:
            st.image(Image.open(pose_file), use_container_width=True, caption="ポーズ参照画像")

        st.divider()

        # 4. 生成設定
        st.subheader("3. 詳細設定")
        custom_prompt = st.text_area("追加プロンプト / 画風指定", placeholder="例：少年漫画風、ドラマチックな照明、線画を強調...", height=100)
        
        num_images = st.slider("生成枚数", min_value=1, max_value=10, value=4, help="一度に生成する画像の枚数です。多いほど時間がかかります。")
        
        model_name = st.selectbox(
            "使用モデル", 
            ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-2.5-flash-image"], 
            index=0,
            help="使用可能なモデルを選択してください。最新の実験モデル(exp)が高精度な場合があります。"
        )

        st.divider()
        
        # 生成ボタン
        generate_btn = st.button("✨ 画像を生成する")

    # --- メインエリア：表示エリア ---
    st.markdown('<h1 class="main-header">🎨 MangaMaker AI</h1>', unsafe_allow_html=True)
    st.markdown("""
    キャラクターの画像とポーズ画像を組み合わせて、新しい漫画の一コマを生成します。
    左側のサイドバーから素材をアップロードしてください。
    """)

    if 'generated_images' not in st.session_state:
        st.session_state.generated_images = []

    # --- 生成ロジック ---
    if generate_btn:
        if not char_files or not pose_file:
            st.error("⚠️ エラー: キャラクター画像とポーズ画像の両方をアップロードしてください。")
        else:
            status_container = st.container()
            with status_container:
                progress_bar = st.progress(0)
                status_text = st.empty()
                status_text.markdown("⏳ **データの準備中...**")

            # データ準備
            character_parts = []
            for cf in char_files:
                bytes_data = cf.getvalue()
                character_parts.append(types.Part.from_bytes(data=bytes_data, mime_type=cf.type))
            
            pose_bytes = pose_file.getvalue()

            # プロンプト（AIへの指示書）
            prompt_text = f"""
            あなたはプロの漫画家アシスタントです。以下の入力に基づいて画像を作成してください。

            【入力情報】
            1. キャラクター参照画像: 添付された画像のキャラクターの外見（顔、髪型、服装）を厳密に再現してください。
            2. ポーズ参照画像: 最後の画像で指定されたポーズ、カメラアングル、構図を正確にトレースしてください。

            【出力要件】
            - 高品質な日本のアニメ・漫画スタイルイラスト。
            - アスペクト比: 16:9。
            - {custom_prompt if custom_prompt else "標準的な漫画スタイル、高品質な線画と着色。"}
            """

            status_text.markdown(f"🎨 **AIが描画中... ({num_images}枚)**")
            
            results = []
            
            # 並列処理実行
            # ワーカー数は生成枚数と最大5の小さい方を採用
            workers = min(num_images, 5)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(generate_single_image, client, prompt_text, character_parts, pose_bytes, model_name) 
                    for _ in range(num_images)
                ]
                
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    result = future.result()
                    if result:
                        results.append(result)
                    # 進捗バーの更新
                    progress_bar.progress((i + 1) / num_images)

            st.session_state.generated_images = results
            status_text.success(f"✅ 生成完了！ {len(results)} 枚の画像が作成されました。")
            
            # 少し待ってからプログレスバーを消す（UX向上のため）
            import time
            time.sleep(1)
            progress_bar.empty()

    # --- 結果ギャラリー表示 ---
    st.subheader("🖼️ 生成結果ギャラリー")
    
    if st.session_state.generated_images:
        # レスポンシブなグリッド表示（枚数に応じて列数を調整）
        cols_count = 2 if len(st.session_state.generated_images) > 1 else 1
        cols = st.columns(cols_count)
        
        for idx, img_bytes in enumerate(st.session_state.generated_images):
            col = cols[idx % cols_count]
            with col:
                image = Image.open(io.BytesIO(img_bytes))
                st.image(image, use_container_width=True, className="generated-img")
                
                # ファイル名用にタイムスタンプなどつけると良いが、ここではシンプルに連番
                btn = st.download_button(
                    label=f"⬇️ 画像 #{idx+1} を保存",
                    data=img_bytes,
                    file_name=f"mangamaker_result_{idx+1}.png",
                    mime="image/png",
                    key=f"dl_{idx}",
                    use_container_width=True
                )
    else:
        # データがない時のプレースホルダー
        st.info("👈 左のサイドバーから設定を行い、「画像を生成する」ボタンを押してください。")
        # 空の状態のプレースホルダー画像（オプション）
        # st.image("https://placehold.co/600x400?text=Your+Art+Here", use_container_width=True)

if __name__ == "__main__":
    main()
