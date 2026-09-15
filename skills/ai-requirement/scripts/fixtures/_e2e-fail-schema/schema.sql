-- 故意错 schema：status NOT NULL，但 DML 写 NULL
-- 用于 E2E 验证 test-mind static_precheck 能捕获 not_null_violation
CREATE TABLE seckill (
  id INT PRIMARY KEY,
  sku_id INT NOT NULL,
  user_id INT NOT NULL,
  status VARCHAR(16) NOT NULL,
  created_at TIMESTAMP
);
