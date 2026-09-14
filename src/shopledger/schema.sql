-- Shop Ledger schema. Snapshots are inserted, never updated, so a modelling
-- change can be replayed across the whole history without spending a credit.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS product (
  product_id      TEXT PRIMARY KEY,
  title           TEXT NOT NULL,
  pdp_url         TEXT NOT NULL,
  image_url       TEXT,
  seller_id       TEXT,
  seller_name     TEXT,
  category_id     TEXT,
  category_name   TEXT,
  first_seen      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  tier            TEXT NOT NULL DEFAULT 'watch'   -- watch | tracked | dropped
);

CREATE TABLE IF NOT EXISTS product_snapshot (
  product_id      TEXT NOT NULL REFERENCES product(product_id),
  captured_at     TEXT NOT NULL,                  -- real fetch time, ISO UTC
  day             TEXT NOT NULL,                  -- YYYY-MM-DD, UTC
  sold_count      INTEGER,
  stock_total     INTEGER,
  rating          REAL,
  review_count    INTEGER,
  min_price       REAL,
  max_price       REAL,
  coupon_price    REAL,
  source          TEXT NOT NULL,                  -- sweep | detail
  raw_json        TEXT,
  PRIMARY KEY (product_id, captured_at)
);
CREATE INDEX IF NOT EXISTS ix_psnap_day ON product_snapshot(product_id, day);

CREATE TABLE IF NOT EXISTS sku_snapshot (
  product_id      TEXT NOT NULL,
  sku_id          TEXT NOT NULL,
  captured_at     TEXT NOT NULL,
  day             TEXT NOT NULL,
  sku_name        TEXT,
  price           REAL,
  stock           INTEGER,
  PRIMARY KEY (product_id, sku_id, captured_at)
);
CREATE INDEX IF NOT EXISTS ix_sku_day ON sku_snapshot(product_id, day);

CREATE TABLE IF NOT EXISTS video (
  item_id         TEXT PRIMARY KEY,
  product_id      TEXT NOT NULL REFERENCES product(product_id),
  url             TEXT NOT NULL,
  title           TEXT,
  author_name     TEXT,
  author_url      TEXT,
  cover_image_url TEXT,
  upload_time     TEXT,
  is_affiliate    INTEGER NOT NULL DEFAULT 0,
  first_seen      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  in_panel        INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_video_product ON video(product_id);

CREATE TABLE IF NOT EXISTS video_snapshot (
  item_id         TEXT NOT NULL REFERENCES video(item_id),
  captured_at     TEXT NOT NULL,
  day             TEXT NOT NULL,
  play_count      INTEGER,
  like_count      INTEGER,
  PRIMARY KEY (item_id, captured_at)
);
CREATE INDEX IF NOT EXISTS ix_vsnap_day ON video_snapshot(item_id, day);

CREATE TABLE IF NOT EXISTS daily_result (
  product_id      TEXT NOT NULL REFERENCES product(product_id),
  day             TEXT NOT NULL,
  units           INTEGER NOT NULL,
  revenue         REAL NOT NULL,
  method          TEXT NOT NULL,      -- sku_stock | sold_delta | reconciled | no_data
  confidence      REAL NOT NULL,      -- coverage coefficient C, 0..1
  restock         INTEGER NOT NULL DEFAULT 0,
  provisional     INTEGER NOT NULL DEFAULT 0,
  unattributed    INTEGER NOT NULL DEFAULT 0,
  sold_delta      INTEGER,
  stock_delta     INTEGER,
  interval_hours  REAL,        -- the real gap between the two snapshots
  partial         INTEGER NOT NULL DEFAULT 0,  -- interval well short of a day
  PRIMARY KEY (product_id, day)
);
CREATE INDEX IF NOT EXISTS ix_result_day ON daily_result(day);

CREATE TABLE IF NOT EXISTS attribution (
  product_id      TEXT NOT NULL,
  item_id         TEXT NOT NULL,
  day             TEXT NOT NULL,
  view_delta      INTEGER NOT NULL,
  share           REAL NOT NULL,
  units           REAL NOT NULL,
  revenue         REAL NOT NULL,
  PRIMARY KEY (product_id, item_id, day)
);
CREATE INDEX IF NOT EXISTS ix_attr_day ON attribution(day);

CREATE TABLE IF NOT EXISTS run_log (
  run_id          TEXT PRIMARY KEY,
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  stage           TEXT NOT NULL,
  credits_before  INTEGER,
  credits_after   INTEGER,
  calls           INTEGER NOT NULL DEFAULT 0,
  errors          INTEGER NOT NULL DEFAULT 0,
  note            TEXT
);
