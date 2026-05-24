# poc-stac-tokyo-taito

台東区のオープンデータ (CSV) を GeoJSON に変換し、STAC API エンドポイントとして提供する POC プロジェクト。

## セットアップ

### 必須環境
- Python >= 3.11
- [uv](https://github.com/astral-sh/uv)

### 依存関係のインストール
```bash
uv sync --all-extras
```

### パイプラインの実行（データ取得・変換・STAC構築）
```bash
uv run python scripts/fetch_and_build.py
```

### サーバーの起動
```bash
uv run uvicorn poc_stac_tokyo_taito.app:app --reload
```

## テストの実行
```bash
uv run pytest
```
