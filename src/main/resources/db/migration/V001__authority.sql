CREATE TABLE ct_clusters (
 cluster_id VARCHAR(64) CHARACTER SET ascii PRIMARY KEY,
 quota_limit INT NOT NULL, policy_version BIGINT NOT NULL DEFAULT 1,
 max_channels INT NOT NULL DEFAULT 32, max_endpoints INT NOT NULL DEFAULT 256,
 recovery_generation BIGINT NOT NULL DEFAULT 1, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 CHECK (quota_limit BETWEEN 0 AND 64), CHECK (max_channels BETWEEN 1 AND 1024), CHECK (max_endpoints BETWEEN 1 AND 65536)
) ENGINE=InnoDB;
CREATE TABLE ct_servers (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, server_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 world_id CHAR(36) CHARACTER SET ascii NOT NULL, session_id CHAR(36) CHARACTER SET ascii NOT NULL,
 fencing_epoch BIGINT NOT NULL, lease_until TIMESTAMP(6) NOT NULL,
 protocol_version INT NOT NULL, format_version INT NOT NULL, capabilities VARCHAR(2048) NOT NULL,
 status VARCHAR(32) NOT NULL, clean_stop BOOLEAN NOT NULL DEFAULT FALSE,
 PRIMARY KEY(cluster_id,server_id), FOREIGN KEY(cluster_id) REFERENCES ct_clusters(cluster_id)
) ENGINE=InnoDB;
CREATE TABLE ct_channels (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 owner_uuid CHAR(36) CHARACTER SET ascii NOT NULL, name VARCHAR(64) NOT NULL,
 version BIGINT NOT NULL DEFAULT 1, status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6), updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,channel_id), KEY owner_channels(cluster_id,owner_uuid,status),
 FOREIGN KEY(cluster_id) REFERENCES ct_clusters(cluster_id)
) ENGINE=InnoDB;
CREATE TABLE ct_members (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 player_uuid CHAR(36) CHARACTER SET ascii NOT NULL, permissions INT NOT NULL,
 joined_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,channel_id,player_uuid),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id)
) ENGINE=InnoDB;
CREATE TABLE ct_invites (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, invite_id CHAR(36) CHARACTER SET ascii NOT NULL,
 channel_id CHAR(36) CHARACTER SET ascii NOT NULL, target_uuid CHAR(36) CHARACTER SET ascii NOT NULL,
 issued_by CHAR(36) CHARACTER SET ascii NOT NULL, kind VARCHAR(16) NOT NULL,
 state VARCHAR(16) NOT NULL DEFAULT 'PENDING', channel_version BIGINT NOT NULL,
 expires_at TIMESTAMP(6) NOT NULL, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,invite_id), KEY target_invites(cluster_id,target_uuid,state,expires_at),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id)
) ENGINE=InnoDB;
CREATE TABLE ct_endpoints (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL,
 server_id VARCHAR(64) CHARACTER SET ascii NOT NULL, world_id CHAR(36) CHARACTER SET ascii NOT NULL,
 device_owner CHAR(36) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii,
 dimension_id VARCHAR(128) CHARACTER SET ascii NOT NULL, pos_x INT NOT NULL, pos_y INT NOT NULL, pos_z INT NOT NULL,
 version BIGINT NOT NULL DEFAULT 1, state VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
 checkpoint BIGINT NOT NULL DEFAULT 0, recovery_generation BIGINT NOT NULL,
 last_epoch BIGINT NOT NULL, pause_reason VARCHAR(96) NOT NULL DEFAULT '',
 last_seen TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,endpoint_id),
 KEY endpoints_channel(cluster_id,channel_id,state), KEY endpoints_player(cluster_id,device_owner),
 KEY endpoints_location(cluster_id,server_id,world_id,dimension_id,pos_x,pos_y,pos_z,state),
 FOREIGN KEY(cluster_id,server_id) REFERENCES ct_servers(cluster_id,server_id),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id)
) ENGINE=InnoDB;
CREATE TABLE ct_player_guards (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, player_uuid CHAR(36) CHARACTER SET ascii NOT NULL,
 PRIMARY KEY(cluster_id,player_uuid), FOREIGN KEY(cluster_id) REFERENCES ct_clusters(cluster_id)
) ENGINE=InnoDB;
CREATE TABLE ct_chunk_grants (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, player_uuid CHAR(36) CHARACTER SET ascii NOT NULL,
 slot_no INT NOT NULL, endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL, request_id CHAR(36) CHARACTER SET ascii NOT NULL,
 state VARCHAR(24) NOT NULL, desired BOOLEAN NOT NULL DEFAULT TRUE, policy_version BIGINT NOT NULL,
 runtime_session CHAR(36) CHARACTER SET ascii, runtime_epoch BIGINT, runtime_until TIMESTAMP(6),
 reason VARCHAR(96) NOT NULL DEFAULT '', created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,player_uuid,slot_no), UNIQUE KEY grant_endpoint(cluster_id,endpoint_id),
 UNIQUE KEY grant_request(cluster_id,request_id),
 FOREIGN KEY(cluster_id,endpoint_id) REFERENCES ct_endpoints(cluster_id,endpoint_id),
 FOREIGN KEY(cluster_id,player_uuid) REFERENCES ct_player_guards(cluster_id,player_uuid), CHECK(slot_no >= 0)
) ENGINE=InnoDB;
CREATE TABLE ct_operations (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, operation_id CHAR(36) CHARACTER SET ascii NOT NULL,
 actor_uuid CHAR(36) CHARACTER SET ascii NOT NULL, kind VARCHAR(32) NOT NULL,
 subject_id CHAR(36) CHARACTER SET ascii NOT NULL, result_code VARCHAR(32) NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,operation_id)
) ENGINE=InnoDB;
CREATE TABLE ct_resources (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, resource_id CHAR(36) CHARACTER SET ascii NOT NULL,
 kind VARCHAR(64) CHARACTER SET ascii NOT NULL, format_version INT NOT NULL,
 payload_hash CHAR(64) CHARACTER SET ascii NOT NULL, payload MEDIUMBLOB NOT NULL,
 PRIMARY KEY(cluster_id,resource_id), UNIQUE KEY resource_hash(cluster_id,kind,payload_hash),
 FOREIGN KEY(cluster_id) REFERENCES ct_clusters(cluster_id)
) ENGINE=InnoDB;
CREATE TABLE ct_balances (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 resource_id CHAR(36) CHARACTER SET ascii NOT NULL, amount BIGINT NOT NULL DEFAULT 0,
 PRIMARY KEY(cluster_id,channel_id,resource_id), CHECK(amount >= 0),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id),
 FOREIGN KEY(cluster_id,resource_id) REFERENCES ct_resources(cluster_id,resource_id)
) ENGINE=InnoDB;
CREATE TABLE ct_transfers (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, transfer_id CHAR(36) CHARACTER SET ascii NOT NULL,
 endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 resource_id CHAR(36) CHARACTER SET ascii NOT NULL, amount BIGINT NOT NULL,
 kind VARCHAR(16) NOT NULL, state VARCHAR(24) NOT NULL, epoch BIGINT NOT NULL,
 remaining BIGINT NOT NULL, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,transfer_id), KEY endpoint_transfers(cluster_id,endpoint_id,state),
 FOREIGN KEY(cluster_id,endpoint_id) REFERENCES ct_endpoints(cluster_id,endpoint_id),
 FOREIGN KEY(cluster_id,channel_id) REFERENCES ct_channels(cluster_id,channel_id),
 FOREIGN KEY(cluster_id,resource_id) REFERENCES ct_resources(cluster_id,resource_id),
 CHECK(amount > 0), CHECK(remaining BETWEEN 0 AND amount)
) ENGINE=InnoDB;
CREATE TABLE ct_demands (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, channel_id CHAR(36) CHARACTER SET ascii NOT NULL,
 endpoint_id CHAR(36) CHARACTER SET ascii NOT NULL, kind VARCHAR(64) CHARACTER SET ascii NOT NULL,
 room BIGINT NOT NULL, expires_at TIMESTAMP(6) NOT NULL, last_grant BIGINT NOT NULL DEFAULT 0,
 PRIMARY KEY(cluster_id,channel_id,endpoint_id,kind), KEY demand_fair(cluster_id,channel_id,kind,last_grant),
 FOREIGN KEY(cluster_id,endpoint_id) REFERENCES ct_endpoints(cluster_id,endpoint_id), CHECK(room >= 0)
) ENGINE=InnoDB;
CREATE TABLE ct_outbox (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 event_id CHAR(36) CHARACTER SET ascii NOT NULL, event_type VARCHAR(32) NOT NULL,
 subject_id CHAR(36) CHARACTER SET ascii NOT NULL, target_server VARCHAR(64) CHARACTER SET ascii,
 published_at TIMESTAMP(6), created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 UNIQUE KEY outbox_event(cluster_id,event_id), KEY unpublished(cluster_id,published_at,id)
) ENGINE=InnoDB;
CREATE TABLE ct_inbox (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, server_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 event_id CHAR(36) CHARACTER SET ascii NOT NULL, received_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,server_id,event_id)
) ENGINE=InnoDB;
CREATE TABLE ct_quarantine (
 cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL, record_id CHAR(36) CHARACTER SET ascii NOT NULL,
 endpoint_id CHAR(36) CHARACTER SET ascii, transfer_id CHAR(36) CHARACTER SET ascii,
 reason VARCHAR(128) NOT NULL, state VARCHAR(16) NOT NULL DEFAULT 'OPEN', details VARCHAR(2048) NOT NULL,
 created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 PRIMARY KEY(cluster_id,record_id), KEY open_quarantine(cluster_id,state,created_at)
) ENGINE=InnoDB;
CREATE TABLE ct_audit (
 id BIGINT AUTO_INCREMENT PRIMARY KEY, cluster_id VARCHAR(64) CHARACTER SET ascii NOT NULL,
 actor_uuid CHAR(36) CHARACTER SET ascii, action VARCHAR(64) NOT NULL, subject_id CHAR(36) CHARACTER SET ascii,
 details VARCHAR(2048) NOT NULL, created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
 KEY audit_cluster(cluster_id,created_at)
) ENGINE=InnoDB;
