# poc-stac-tokyo-taito

東京都台東区のオープンデータと GTFS バスデータを組み合わせ、2つのことを同時に検証する PoC。

1. **公共アセットの STAC 化** — 東京都オープンデータカタログの台東区 CKAN データセットを取得し、CSV を GeoJSON に変換して STAC Item / Collection として整理。静的な公共施設データを MVT として配信する。

2. **状態タイルの実験** — めぐりん GTFS データから現在時刻または指定時刻のバス位置を停留所間で補間し、`/state/{z}/{x}/{y}` から MVT として配信する。MapLibre GL JS の `addProtocol()` と `expires` を利用し、`setTiles()` や `setData()` に依存せず状態タイルを滑らかに更新する。

---

## 状態タイル

**状態タイル**とは、ある時点 `t` における移動体・公共アセット等の状態を、`z/x/y` のタイル単位でサーバー側が計算して返す MVT である。

通常の静的 vector tile は同じ `z/x/y` に対して常に同じ内容を返すが、状態タイルは `?seconds=<t>` パラメータによって返す中身が変わる。既存の dynamic vector tile / on-the-fly MVT / realtime map と設計的に近いが、この PoC では「状態の更新」と「MapLibre のタイルライフサイクル」を接続することに焦点を当てている。

この PoC における状態タイルの実体は、めぐりん GTFS を使い時刻 `seconds` におけるバス位置をサーバー側で補間した MVT である。

---

## MapLibre addProtocol による状態タイル更新

状態タイルのビューアー (`docs/index.html`) は以下の流れで動作する。

1. MapLibre の vector source は `stateTile://{z}/{x}/{y}` を参照する
2. `maplibregl.addProtocol('stateTile', handler)` がその URL を処理する
3. protocol handler はグローバル変数 `stateTileSecs` を読み取り、`/state/{z}/{x}/{y}?seconds=<stateTileSecs>` を fetch する
4. サーバーは指定時刻のめぐりん位置を MVT bytes として返す
5. handler は `{ data, expires: new Date(Date.now() + 1500) }` を返す
6. MapLibre はこのタイルを 1.5 秒 TTL のキャッシュとして扱い、期限切れ後にバックグラウンドで再取得する
7. 古いタイルを表示し続けながら新しいタイルへ差し替えるため、視覚的なちらつきが発生しない

**重要:** `setTiles()` を毎回呼ばないことがポイントである。`setTiles()` は MapLibre のグローバルタイルキャッシュを全消去するため、`showTileBoundaries` を含む全レイヤーのちらつきを引き起こす。`addProtocol` + `expires` によるタイルライフサイクムの活用はこれを回避するための実験的アプローチである。

---

## API エンドポイント

### STAC

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/stac/` | STAC Catalog landing page |
| `GET` | `/stac/collections` | STAC Collection 一覧 |
| `GET` | `/stac/collections/{collection_id}` | Collection 詳細 |
| `GET` | `/stac/collections/{collection_id}/items` | Collection 内の Item 一覧 |
| `GET` | `/stac/collections/{collection_id}/items/{item_id}` | Item 詳細 |
| `GET` | `/stac/search` | bbox / datetime / collections / ids による簡易検索 |
| `POST` | `/stac/search` | STAC Item Search 風の簡易検索 |

### MVT

| メソッド | パス | 説明 |
|---|---|---|
| `GET` | `/tiles/{z}/{x}/{y}` | CKAN 由来の公共施設 GeoJSON を統合した静的 MVT |
| `GET` | `/state/{z}/{x}/{y}` | 指定時刻のめぐりん位置を返す状態 MVT |
| `GET` | `/state/buses` | 指定時刻のめぐりん位置を返す GeoJSON（デバッグ・比較用。主経路は `/state/{z}/{x}/{y}`） |

---

## データフロー

```text
CKAN API
  ↓
scripts/fetch_and_build.py
  ↓
CSV download / parse
  ↓
address geocoding
  ↓
GeoJSON
  ↓
STAC Items / Collections
  ↓
/tiles/{z}/{x}/{y}


GTFS
  ↓
MegurinSimulator
  ↓
time-based interpolation
  ↓
/state/buses（デバッグ・比較用 GeoJSON）
/state/{z}/{x}/{y}（状態 MVT）
  ↓
MapLibre addProtocol('stateTile') + expires
  ↓
smooth dynamic state tile rendering
```

---

## ディレクトリ構成

```text
.
├── scripts/
│   └── fetch_and_build.py        # CKAN取得→CSV→GeoJSON→STAC構築パイプライン
├── src/poc_stac_tokyo_taito/
│   ├── app.py                    # FastAPI アプリ（STAC API・MVT・状態タイル endpoints）
│   ├── ckan_client.py            # 東京都オープンデータ CKAN API クライアント
│   ├── csv_parser.py             # CSV パーサー（台東区データセット対応）
│   ├── geocoder.py               # 住所→座標 ジオコーダー
│   ├── geojson_converter.py      # GeoJSON 変換・正規化
│   ├── stac_builder.py           # STAC Item / Collection 生成
│   └── megurin_simulator.py      # GTFS 読み込み・時刻補間・バス位置計算
├── docs/
│   └── index.html                # MapLibre GL JS ビューアー（状態タイル対応）
├── tests/                        # pytest テストスイート
├── Dockerfile                    # マルチステージビルド（uv + python:3.12-slim）
└── k8s/
    └── knative-service.yaml      # Knative Service マニフェスト
```

---

## セットアップ

### 必須環境

- Python >= 3.11
- [uv](https://github.com/astral-sh/uv)

### 依存関係のインストール

```bash
uv sync --all-extras
```

### データ取得・変換・STAC構築

```bash
uv run python scripts/fetch_and_build.py
```

### サーバーの起動

```bash
uv run uvicorn poc_stac_tokyo_taito.app:app --reload
```

### テストの実行

```bash
uv run pytest
```

### Docker ビルドと Knative デプロイ

```bash
docker build -t poc-stac-tokyo-taito:0.1.0 .
kubectl apply -f k8s/knative-service.yaml
```

---

## Limitations（制約・留意事項）

- **STAC API は subset 実装である。** 完全な STAC API 仕様への準拠を目的としておらず、PoC に必要な範囲の最小実装である。
- **GTFS の運行日判定は簡易実装である。** 祝日・運休日・`calendar_dates.txt` 等の完全な解釈は目的外であり、実際の運行スケジュールと差異が生じる場合がある。
- **バス位置は直線補間である。** 停留所間を直線で補間しており、道路形状や GTFS shapes を厳密に追跡しているわけではない。
- **状態タイルは全タイルが同一時刻の完全なスナップショットになるとは限らない。** タイルごとに個別に再検証されるため、取得タイミングによってわずかな時刻差が生じうる。
- **本番運用品質ではない。** この PoC の主眼は、STAC 化された公共アセットと動的状態タイルを同一の MapLibre ビューアで扱う実験であり、スケーラビリティや信頼性は考慮外である。
