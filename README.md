# ryouiku-dev/blog

WordPress向けの記事下書きを作成し、必要に応じてWordPress REST APIで投稿できる軽量なブログ作成ツールです。

## できること

- タイトル、トピック、読者、SEOキーワードからWordPressブロックエディター互換のHTMLを生成
- 下書きHTMLとメタデータJSONをローカルに保存
- WordPressのアプリケーションパスワードを使って、下書き・公開・承認待ちなどのステータスで投稿を作成
- Python標準ライブラリのみで動作

## 必要環境

- Python 3.10以上
- WordPressへ投稿する場合は、WordPressユーザーのアプリケーションパスワード

## 使い方

ローカルに下書きを生成します。

```bash
python wordpress_blog_tool.py \
  --title "家庭で始める療育のポイント" \
  --topic "家庭療育" \
  --audience "保護者" \
  --keyword "療育,発達支援,家庭でできること"
```

生成物はデフォルトで `drafts/` に保存されます。

- `drafts/<slug>.html`: WordPressブロックエディターに貼り付けられるHTML
- `drafts/<slug>.json`: タイトル、抜粋、キーワードなどのメタデータ

## WordPressへ投稿する

WordPress管理画面でアプリケーションパスワードを作成し、環境変数またはCLI引数で渡してください。

```bash
export WP_URL="https://example.com"
export WP_USERNAME="editor"
export WP_APP_PASSWORD="xxxx xxxx xxxx xxxx xxxx xxxx"

python wordpress_blog_tool.py \
  --title "家庭で始める療育のポイント" \
  --topic "家庭療育" \
  --keyword "療育,発達支援" \
  --publish \
  --status draft
```

`--status` は `draft`, `publish`, `pending`, `private`, `future` を指定できます。安全のためデフォルトは `draft` です。

## テスト

```bash
python -m unittest discover -s tests
```
