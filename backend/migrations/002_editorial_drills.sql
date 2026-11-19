-- 编辑演练：冻结会话 → 分批受理接续 → 合齐后统一求解 → 逐条路线与覆盖核对。
CREATE TABLE IF NOT EXISTS reading_trails (
  id INT PRIMARY KEY AUTO_INCREMENT,
  source_id INT NOT NULL,
  title VARCHAR(160) NOT NULL,
  state VARCHAR(20) NOT NULL DEFAULT 'collecting',
  error TEXT,
  frozen_catalog JSON,
  catalog_sha256 VARCHAR(64) NOT NULL,
  meta JSON,
  route_count INT,
  total_steps INT,
  closed_routes INT,
  continuation_count INT,
  off_board INT,
  off_board_covered INT,
  covered INT,
  complete TINYINT(1) NOT NULL DEFAULT 0,
  memory_limit_mb INT NOT NULL DEFAULT 192,
  intake_peak_mb INT,
  solve_peak_mb INT,
  created_at VARCHAR(40) NOT NULL,
  completed_at VARCHAR(40),
  CONSTRAINT fk_trail_source FOREIGN KEY (source_id) REFERENCES reading_collections(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS trail_batches (
  id INT PRIMARY KEY AUTO_INCREMENT,
  trail_id INT NOT NULL,
  `index` INT NOT NULL,
  state VARCHAR(20) NOT NULL DEFAULT 'accepted',
  continuations INT NOT NULL,
  sha256 VARCHAR(64) NOT NULL,
  bytes INT DEFAULT 0,
  receipt JSON,
  created_at VARCHAR(40) NOT NULL,
  UNIQUE KEY uq_trail_batch (trail_id, `index`),
  CONSTRAINT fk_batch_trail FOREIGN KEY (trail_id) REFERENCES reading_trails(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS trail_routes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  trail_id INT NOT NULL,
  route_index INT NOT NULL,
  closed TINYINT(1) NOT NULL DEFAULT 0,
  step_count INT NOT NULL,
  nodes JSON NOT NULL,
  steps JSON NOT NULL,
  UNIQUE KEY uq_trail_route (trail_id, route_index),
  CONSTRAINT fk_route_trail FOREIGN KEY (trail_id) REFERENCES reading_trails(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS trail_coverage (
  id INT PRIMARY KEY AUTO_INCREMENT,
  trail_id INT NOT NULL,
  from_chapter VARCHAR(600) NOT NULL,
  to_chapter VARCHAR(600) NOT NULL,
  measured INT NOT NULL,
  walked INT NOT NULL,
  covered TINYINT(1) NOT NULL,
  on_board TINYINT(1) NOT NULL,
  KEY ix_cover_trail (trail_id, id),
  KEY ix_cover_missing (trail_id, covered),
  CONSTRAINT fk_cover_trail FOREIGN KEY (trail_id) REFERENCES reading_trails(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
