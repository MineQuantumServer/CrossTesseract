CREATE TABLE ct_stock_requests (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 request_id CHAR(36) CHARACTER SET ascii NOT NULL,
 endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL,
 channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 resource_id CHAR(36) CHARACTER SET ascii NOT NULL,
 actor_uuid CHAR(36) CHARACTER SET ascii NOT NULL,
 amount BIGINT NOT NULL, remaining BIGINT NOT NULL,
 state VARCHAR(24) NOT NULL DEFAULT 'PENDING',
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 expires_at TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(cluster_id,request_id),
 KEY stock_endpoint(cluster_id,endpoint_id,state,created_at),
 FOREIGN KEY(cluster_id,endpoint_id) REFERENCES ct_endpoints(cluster_id,endpoint_id),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id),
 FOREIGN KEY(cluster_id,resource_id) REFERENCES ct_resources(cluster_id,resource_id),
 CHECK(amount>0), CHECK(remaining>=0 AND remaining<=amount)
) ENGINE=InnoDB;
