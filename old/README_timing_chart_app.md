# タイミングチャートアプリ MVP

## 概要
Python + PySide6 で作成した、PC上で動作するタイミングチャートアプリの初版です。

### 実装済み
- 3タブ構成
  - グラフ
  - 機器一覧
  - 動作設定
- 階層構造
  - 大項目 / 中項目 / 小項目
- ID付与
  - 階層項目ID
  - 動作定義ID
  - 動作設定ID
- 動作種別
  - ON/OFF
  - ポイント移動
- 依存関係
  - manual
  - after_finish
  - after_start
- チャート上クリックによる依存設定
  - リンクモードON
  - 元の動作をクリック
  - 先の動作をクリック
  - 完了後開始 / 同時開始 を選択
- JSON保存 / 読み込み

## セットアップ
```bash
pip install -r requirements.txt
python timing_chart_app.py
```

## データ構造の考え方
- hierarchy_items
  - 大項目 / 中項目 / 小項目
- action_definitions
  - 小項目に紐づく動作マスタ
  - 例: Z軸の「位置移動」
- operations
  - 実際のタイミング設定
  - 時間、開始条件、依存先、開始値、終了値

## 今後追加しやすい拡張候補
- グラフ上ドラッグで時間変更
- ズーム / スクロール / スナップ
- 複数系列の並列制御チェック
- CSV / Excel 出力
- 依存関係の詳細条件
  - 完了
  - 立上り
  - 立下り
  - AND / OR 条件
- 小項目ごとの色設定
- Undo / Redo
- 設備テンプレート管理
