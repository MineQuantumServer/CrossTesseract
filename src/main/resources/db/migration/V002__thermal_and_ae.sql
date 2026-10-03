ALTER TABLE ct_demands ADD COLUMN profile_hash CHAR(64) CHARACTER SET ascii NULL;
ALTER TABLE ct_demands ADD COLUMN quantum BIGINT NOT NULL DEFAULT 1;
CREATE TABLE ct_thermal_pools (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 microjoules BIGINT NOT NULL DEFAULT 0, capacity DOUBLE NOT NULL DEFAULT 10000,
 PRIMARY KEY(cluster_id,channel_id),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id),
 CHECK(microjoules >= 0), CHECK(capacity >= 1)
) ENGINE=InnoDB;
CREATE TABLE ct_heat_exchanges (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, exchange_id CHAR(36) CHARACTER SET ascii NOT NULL,
 endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 signed_microjoules BIGINT NOT NULL, local_before BIGINT NOT NULL, local_capacity DOUBLE NOT NULL,
 pool_before BIGINT NOT NULL, pool_after BIGINT NOT NULL,
 state VARCHAR(24) NOT NULL DEFAULT 'PREPARED', epoch BIGINT NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,exchange_id), KEY heat_pending(cluster_id,channel_id,state),
 KEY heat_endpoint(cluster_id,endpoint_id,state),
 FOREIGN KEY(cluster_id,endpoint_id) REFERENCES ct_endpoints(cluster_id,endpoint_id),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id),
 CHECK(signed_microjoules <> 0),CHECK(local_before >= 0),CHECK(local_capacity >= 1),CHECK(pool_after >= 0)
) ENGINE=InnoDB;
CREATE TABLE ct_ae_networks (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL,
 channel_id CHAR(36) CHARACTER SET ascii NOT NULL, server_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 network_id CHAR(36) CHARACTER SET ascii NOT NULL, epoch BIGINT NOT NULL,
 used_channels INT NOT NULL, active BOOLEAN NOT NULL, controller_state VARCHAR(32) NOT NULL,
 lease_until TIMESTAMP(6) NOT NULL,
 PRIMARY KEY(cluster_id,endpoint_id), KEY ae_channel(cluster_id,channel_id,server_id,network_id),
 FOREIGN KEY(cluster_id,endpoint_id) REFERENCES ct_endpoints(cluster_id,endpoint_id),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id),
 CHECK(used_channels BETWEEN 0 AND 4096)
) ENGINE=InnoDB;
