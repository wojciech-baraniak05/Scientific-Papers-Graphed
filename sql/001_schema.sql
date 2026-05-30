SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS countries (
    code             CHAR(2)       NOT NULL,
    iso3             CHAR(3)       NULL,
    name             VARCHAR(128)  NULL,
    gdp_usd          DOUBLE        NULL,
    gdp_year         SMALLINT      NULL,
    population       BIGINT        NULL,
    population_year  SMALLINT      NULL,
    num_universities INT           NULL,
    PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS universities (
    id           INT           NOT NULL AUTO_INCREMENT,
    name         VARCHAR(512)  NOT NULL,
    country_code CHAR(2)       NULL,
    country_name VARCHAR(128)  NULL,
    web_page     VARCHAR(512)  NULL,
    domains      JSON          NULL,
    PRIMARY KEY (id),
    KEY ix_universities_country_code (country_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS fields (
    id          VARCHAR(20)  NOT NULL,
    name        VARCHAR(255) NULL,
    domain_id   VARCHAR(20)  NULL,
    domain_name VARCHAR(255) NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS authors (
    id           VARCHAR(50)  NOT NULL,
    display_name VARCHAR(512) NULL,
    orcid        VARCHAR(64)  NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS institutions (
    id           VARCHAR(50)  NOT NULL,
    display_name VARCHAR(512) NULL,
    country_code CHAR(2)      NULL,
    type         VARCHAR(32)  NULL,
    ror          VARCHAR(255) NULL,
    PRIMARY KEY (id),
    KEY ix_institutions_country_code (country_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS papers (
    id                     VARCHAR(50)  NOT NULL,
    doi                    VARCHAR(255) NULL,
    title                  TEXT         NULL,
    publication_year       SMALLINT     NULL,
    cited_by_count         INT          NULL,
    referenced_works_count INT          NULL,
    is_open_access         TINYINT(1)   NULL,
    oa_status              VARCHAR(20)  NULL,
    oa_url                 VARCHAR(1024) NULL,
    is_educational         TINYINT(1)   NULL,
    primary_field_id       VARCHAR(20)  NULL,
    primary_field_name     VARCHAR(255) NULL,
    primary_domain_id      VARCHAR(20)  NULL,
    primary_domain_name    VARCHAR(255) NULL,
    abstract               MEDIUMTEXT   NULL,
    ingested               TINYINT(1)   NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY ix_papers_cited_by_count (cited_by_count),
    KEY ix_papers_primary_field_id (primary_field_id),
    KEY ix_papers_primary_domain_id (primary_domain_id),
    KEY ix_papers_ingested (ingested)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id        VARCHAR(50) NOT NULL,
    author_id       VARCHAR(50) NOT NULL,
    author_position VARCHAR(16) NULL,
    PRIMARY KEY (paper_id, author_id),
    KEY ix_paper_authors_author_id (author_id),
    CONSTRAINT fk_pa_paper  FOREIGN KEY (paper_id)  REFERENCES papers (id)  ON DELETE CASCADE,
    CONSTRAINT fk_pa_author FOREIGN KEY (author_id) REFERENCES authors (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS paper_institutions (
    paper_id       VARCHAR(50) NOT NULL,
    institution_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (paper_id, institution_id),
    KEY ix_paper_institutions_institution_id (institution_id),
    CONSTRAINT fk_pi_paper FOREIGN KEY (paper_id)       REFERENCES papers (id)       ON DELETE CASCADE,
    CONSTRAINT fk_pi_inst  FOREIGN KEY (institution_id) REFERENCES institutions (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS paper_countries (
    paper_id     VARCHAR(50) NOT NULL,
    country_code CHAR(2)     NOT NULL,
    PRIMARY KEY (paper_id, country_code),
    KEY ix_paper_countries_country_code (country_code),
    CONSTRAINT fk_pc_paper   FOREIGN KEY (paper_id)     REFERENCES papers (id)     ON DELETE CASCADE,
    CONSTRAINT fk_pc_country FOREIGN KEY (country_code) REFERENCES countries (code) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS paper_references (
    citing_id     VARCHAR(50) NOT NULL,
    referenced_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (citing_id, referenced_id),
    KEY ix_paper_references_referenced_id (referenced_id),
    CONSTRAINT fk_pr_citing     FOREIGN KEY (citing_id)     REFERENCES papers (id) ON DELETE CASCADE,
    CONSTRAINT fk_pr_referenced FOREIGN KEY (referenced_id) REFERENCES papers (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS ingest_runs (
    id               INT          NOT NULL AUTO_INCREMENT,
    scope            VARCHAR(128) NULL,
    started_at       DATETIME     NULL,
    finished_at      DATETIME     NULL,
    papers_ingested  INT          NULL,
    db_size_bytes    BIGINT       NULL,
    status           VARCHAR(32)  NULL,
    message          TEXT         NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
