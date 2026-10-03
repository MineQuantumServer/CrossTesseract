ALTER TABLE ct_clusters ADD COLUMN history_limit INT NOT NULL DEFAULT 500000;
-- @statement
CREATE TABLE ct_history_buckets (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, server_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 used BIGINT NOT NULL DEFAULT 0, PRIMARY KEY(cluster_id,server_id),
 FOREIGN KEY(cluster_id,server_id) REFERENCES ct_servers(cluster_id,server_id), CHECK(used>=0)
) ENGINE=InnoDB;
-- @statement
INSERT INTO ct_history_buckets(cluster_id,server_id,used)
 SELECT e.cluster_id,e.server_id,COUNT(*) FROM ct_transfers t JOIN ct_endpoints e ON e.cluster_id=t.cluster_id AND e.endpoint_id=t.endpoint_id GROUP BY e.cluster_id,e.server_id;
-- @statement
INSERT INTO ct_history_buckets(cluster_id,server_id,used)
 SELECT e.cluster_id,e.server_id,COUNT(*) FROM ct_heat_exchanges h JOIN ct_endpoints e ON e.cluster_id=h.cluster_id AND e.endpoint_id=h.endpoint_id GROUP BY e.cluster_id,e.server_id
 ON DUPLICATE KEY UPDATE used=used+VALUES(used);
-- @statement
CREATE INDEX ct_transfer_retention ON ct_transfers(cluster_id,created_at,state);
-- @statement
CREATE INDEX ct_heat_retention ON ct_heat_exchanges(cluster_id,created_at,state);
-- @statement
CREATE INDEX ct_inbox_retention ON ct_inbox(cluster_id,received_at);
