-- Fennsill cloud + factory inventory (Microsoft SQL Server)
-- Apply on the database named in FENNSILL_SQL_CONNECTION.
-- Never store MCU device_secret_hex or the factory master key here.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

/* -------------------------------------------------------------------------- */
/* users                                                                      */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.users', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.users (
        id              BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_users PRIMARY KEY,
        email           NVARCHAR(200) NOT NULL,
        password_hash   NVARCHAR(200) NOT NULL,  -- salt$hex digest (PBKDF2-SHA256)
        created_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_users_created_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT UQ_users_email UNIQUE (email)
    );
END
GO

/* -------------------------------------------------------------------------- */
/* sessions — user bearer for account UI + MCP                                */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.sessions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.sessions (
        token           NVARCHAR(128) NOT NULL CONSTRAINT PK_sessions PRIMARY KEY,
        user_id         BIGINT NOT NULL
            CONSTRAINT FK_sessions_user REFERENCES dbo.users(id),
        created_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_sessions_created_at DEFAULT (SYSUTCDATETIME()),
        expires_at      DATETIME2(0) NULL
    );
    CREATE INDEX IX_sessions_user ON dbo.sessions(user_id);
END
GO

/* -------------------------------------------------------------------------- */
/* manufactured_devices — factory inventory (presave before ship)             */
/* product_id / box_serial = FS-YYMM-NNNNNN                                   */
/* device_id = FS + 12 uppercase hex (eFuse-derived)                          */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.manufactured_devices', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.manufactured_devices (
        id                  BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_manufactured_devices PRIMARY KEY,
        device_id           CHAR(14) NOT NULL,          -- ^FS[0-9A-F]{12}$
        box_serial          CHAR(14) NOT NULL,          -- FS-YYMM-NNNNNN (product id)
        key_fingerprint     NVARCHAR(64) NOT NULL
            CONSTRAINT DF_mfg_key_fingerprint DEFAULT (N''),
        fw_version          NVARCHAR(32) NOT NULL
            CONSTRAINT DF_mfg_fw_version DEFAULT (N''),
        provisioned_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_mfg_provisioned_at DEFAULT (SYSUTCDATETIME()),
        claimed_user_id     BIGINT NULL
            CONSTRAINT FK_mfg_claimed_user REFERENCES dbo.users(id),
        claimed_at          DATETIME2(0) NULL,
        CONSTRAINT UQ_mfg_device_id UNIQUE (device_id),
        CONSTRAINT UQ_mfg_box_serial UNIQUE (box_serial),
        CONSTRAINT CK_mfg_device_id CHECK (
            device_id LIKE N'FS[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F]'
        ),
        CONSTRAINT CK_mfg_box_serial CHECK (
            box_serial LIKE N'FS-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]'
        )
    );
    CREATE INDEX IX_mfg_unclaimed ON dbo.manufactured_devices(box_serial)
        WHERE claimed_user_id IS NULL;
END
GO

/* -------------------------------------------------------------------------- */
/* devices — buyer-linked panels                                              */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.devices', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.devices (
        id              BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_devices PRIMARY KEY,
        user_id         BIGINT NOT NULL
            CONSTRAINT FK_devices_user REFERENCES dbo.users(id),
        device_id       CHAR(14) NOT NULL,
        box_serial      CHAR(14) NOT NULL,
        label           NVARCHAR(100) NOT NULL
            CONSTRAINT DF_devices_label DEFAULT (N''),
        linked_at       DATETIME2(0) NOT NULL
            CONSTRAINT DF_devices_linked_at DEFAULT (SYSUTCDATETIME()),
        last_seen_at    DATETIME2(0) NULL,
        CONSTRAINT UQ_devices_device_id UNIQUE (device_id),
        CONSTRAINT UQ_devices_box_serial UNIQUE (box_serial)
    );
    CREATE INDEX IX_devices_user ON dbo.devices(user_id);
END
GO

/* -------------------------------------------------------------------------- */
/* device_tokens — cloud device keys for FennSill Agent                       */
/* Prefer storing token_hash; token_plaintext only if mint-once UX requires it */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.device_tokens', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.device_tokens (
        id              BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_device_tokens PRIMARY KEY,
        token_hash      NVARCHAR(128) NOT NULL,
        token_hint      NVARCHAR(16) NOT NULL
            CONSTRAINT DF_device_tokens_hint DEFAULT (N''),
        user_id         BIGINT NOT NULL
            CONSTRAINT FK_device_tokens_user REFERENCES dbo.users(id),
        device_id       CHAR(14) NOT NULL,
        created_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_device_tokens_created_at DEFAULT (SYSUTCDATETIME()),
        revoked         BIT NOT NULL
            CONSTRAINT DF_device_tokens_revoked DEFAULT (0),
        CONSTRAINT UQ_device_tokens_hash UNIQUE (token_hash)
    );
    CREATE INDEX IX_device_tokens_device ON dbo.device_tokens(device_id, revoked);
    CREATE INDEX IX_device_tokens_user ON dbo.device_tokens(user_id);
END
GO

/* -------------------------------------------------------------------------- */
/* access_subscriptions — one row per account; trial period = 60 days         */
/* status: pending | active | inactive                                        */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.access_subscriptions', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.access_subscriptions (
        user_id             BIGINT NOT NULL
            CONSTRAINT PK_access_subscriptions PRIMARY KEY
            CONSTRAINT FK_access_subscriptions_user REFERENCES dbo.users(id),
        status              NVARCHAR(16) NOT NULL
            CONSTRAINT DF_access_subscriptions_status DEFAULT (N'pending'),
        started_at          DATETIME2(0) NULL,
        current_period_end  DATETIME2(0) NULL,
        updated_at          DATETIME2(0) NOT NULL
            CONSTRAINT DF_access_subscriptions_updated_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_access_subscriptions_status CHECK (
            status IN (N'pending', N'active', N'inactive')
        )
    );
END
GO

/* -------------------------------------------------------------------------- */
/* push_jobs — MCP → agent queue                                              */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.push_jobs', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.push_jobs (
        id              NVARCHAR(64) NOT NULL CONSTRAINT PK_push_jobs PRIMARY KEY,
        user_id         BIGINT NOT NULL
            CONSTRAINT FK_push_jobs_user REFERENCES dbo.users(id),
        device_id       CHAR(14) NOT NULL,
        job_type        NVARCHAR(32) NOT NULL,
        html            NVARCHAR(MAX) NULL,
        svg             NVARCHAR(MAX) NULL,
        title           NVARCHAR(200) NOT NULL
            CONSTRAINT DF_push_jobs_title DEFAULT (N''),
        feed_kind       NVARCHAR(64) NULL,
        interval_sec    INT NULL,
        status          NVARCHAR(16) NOT NULL,  -- queued | claimed | done | failed
        error           NVARCHAR(500) NOT NULL
            CONSTRAINT DF_push_jobs_error DEFAULT (N''),
        created_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_push_jobs_created_at DEFAULT (SYSUTCDATETIME()),
        updated_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_push_jobs_updated_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT CK_push_jobs_status CHECK (
            status IN (N'queued', N'claimed', N'done', N'failed')
        )
    );
    CREATE INDEX IX_jobs_claim
        ON dbo.push_jobs(user_id, device_id, status, created_at);
END
GO

/* -------------------------------------------------------------------------- */
/* push_rate — ~30 pushes / 10 min per account+device                         */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.push_rate', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.push_rate (
        id              BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_push_rate PRIMARY KEY,
        user_id         BIGINT NOT NULL,
        device_id       CHAR(14) NOT NULL,
        created_at      DATETIME2(0) NOT NULL
            CONSTRAINT DF_push_rate_created_at DEFAULT (SYSUTCDATETIME())
    );
    CREATE INDEX IX_push_rate ON dbo.push_rate(user_id, device_id, created_at);
END
GO

/* -------------------------------------------------------------------------- */
/* update_manifests — OTA channel metadata (read-only to clients)             */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.update_manifests', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.update_manifests (
        channel         NVARCHAR(64) NOT NULL CONSTRAINT PK_update_manifests PRIMARY KEY,
        version         NVARCHAR(64) NOT NULL,
        url             NVARCHAR(500) NOT NULL,
        sha256          NVARCHAR(64) NOT NULL,
        published_at    DATETIME2(0) NOT NULL
            CONSTRAINT DF_update_manifests_published_at DEFAULT (SYSUTCDATETIME())
    );
END
GO

/* -------------------------------------------------------------------------- */
/* Optional: factory import audit (who uploaded which unit)                   */
/* -------------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.factory_imports', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.factory_imports (
        id              BIGINT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_factory_imports PRIMARY KEY,
        device_id       CHAR(14) NOT NULL,
        box_serial      CHAR(14) NOT NULL,
        imported_at     DATETIME2(0) NOT NULL
            CONSTRAINT DF_factory_imports_imported_at DEFAULT (SYSUTCDATETIME()),
        source          NVARCHAR(64) NOT NULL
            CONSTRAINT DF_factory_imports_source DEFAULT (N'factory'),
        actor           NVARCHAR(128) NOT NULL
            CONSTRAINT DF_factory_imports_actor DEFAULT (N'')
    );
    CREATE INDEX IX_factory_imports_serial ON dbo.factory_imports(box_serial);
END
GO
