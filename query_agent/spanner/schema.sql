-- ============================================================================
-- Cloud Spanner DDL: OKF Knowledge Graph, Vector, Full-Text & Data Lineage
-- Specification: SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT
-- ============================================================================

CREATE TABLE RawSourceDocuments (
  source_id STRING(128) NOT NULL,
  filename STRING(512) NOT NULL,
  subfolder STRING(64) NOT NULL,
  doc_code STRING(128),
  revision STRING(32),
  md5_hash STRING(64),
  gcs_uri STRING(1024),
  ingested_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (source_id);

CREATE TABLE OkfConcepts (
  concept_id STRING(256) NOT NULL,
  category STRING(64) NOT NULL,
  name STRING(512) NOT NULL,
  description STRING(MAX),
  unit STRING(64),
  trust_tier STRING(64) NOT NULL,
  has_conflict BOOL NOT NULL,
  conflict_count INT64 NOT NULL,
  frontmatter_json JSON,
  body_markdown STRING(MAX) NOT NULL,
  md5_hash STRING(64) NOT NULL,
  bundle_version STRING(64) NOT NULL,
  gcs_uri STRING(1024),
  updated_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  ConceptTokens TOKENLIST AS (
    TOKENIZE_FULLTEXT(CONCAT(concept_id, ' ', name, ' ', IFNULL(description, ''), ' ', IFNULL(unit, '')))
  ) HIDDEN
) PRIMARY KEY (concept_id);

CREATE SEARCH INDEX idx_okf_concepts_fts ON OkfConcepts(ConceptTokens);

CREATE TABLE OkfSectionChunks (
  chunk_id STRING(128) NOT NULL,
  concept_id STRING(256) NOT NULL,
  category STRING(64) NOT NULL,
  unit STRING(64),
  section_heading STRING(256) NOT NULL,
  chunk_index INT64 NOT NULL,
  header_preserved_markdown STRING(MAX) NOT NULL,
  has_conflict BOOL NOT NULL,
  embedding ARRAY<FLOAT32>(vector_length=>768),
  ChunkTokens TOKENLIST AS (
    TOKENIZE_FULLTEXT(CONCAT(concept_id, ' ', section_heading, ' ', header_preserved_markdown))
  ) HIDDEN,
  SubTokens TOKENLIST AS (
    TOKENIZE_SUBSTRING(CONCAT(concept_id, ' ', section_heading, ' ', header_preserved_markdown))
  ) HIDDEN
) PRIMARY KEY (chunk_id);

CREATE SEARCH INDEX idx_okf_chunks_fts
  ON OkfSectionChunks(ChunkTokens, SubTokens)
  STORING (concept_id, category, unit, section_heading, has_conflict);

CREATE TABLE EngineeringEntities (
  entity_id STRING(256) NOT NULL,
  entity_type STRING(64) NOT NULL,
  canonical_tag STRING(128) NOT NULL,
  name STRING(512) NOT NULL,
  equipment_class STRING(128),
  unit STRING(64),
  concept_id STRING(256) NOT NULL,
  EntityTokens TOKENLIST AS (
    TOKENIZE_SUBSTRING(CONCAT(canonical_tag, ' ', name, ' ', IFNULL(equipment_class, ''), ' ', IFNULL(unit, '')))
  ) HIDDEN
) PRIMARY KEY (entity_id);

CREATE SEARCH INDEX idx_engineering_entities_fts ON EngineeringEntities(EntityTokens);

CREATE INDEX idx_engineering_entities_tag ON EngineeringEntities(canonical_tag);

CREATE TABLE FactAssertions (
  fact_id STRING(128) NOT NULL,
  concept_id STRING(256) NOT NULL,
  entity_id STRING(256),
  section_heading STRING(256) NOT NULL,
  parameter_name STRING(512) NOT NULL,
  parameter_value STRING(MAX) NOT NULL,
  parameter_unit STRING(128),
  has_conflict BOOL NOT NULL,
  conflict_note STRING(MAX),
  bundle_version STRING(64) NOT NULL,
  extracted_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true),
  FactTokens TOKENLIST AS (
    TOKENIZE_FULLTEXT(CONCAT(concept_id, ' ', section_heading, ' ', parameter_name, ' ', parameter_value, ' ', IFNULL(conflict_note, '')))
  ) HIDDEN
) PRIMARY KEY (fact_id);

CREATE SEARCH INDEX idx_fact_assertions_fts ON FactAssertions(FactTokens);

CREATE INDEX idx_fact_assertions_concept ON FactAssertions(concept_id, has_conflict);

CREATE TABLE ProcessConnections (
  edge_id STRING(128) NOT NULL,
  from_entity_id STRING(256) NOT NULL,
  to_entity_id STRING(256) NOT NULL,
  stream_or_line_id STRING(256) NOT NULL,
  fluid_service STRING(512),
  temperature STRING(128),
  pressure STRING(128),
  flow_rate STRING(128),
  source_concept_id STRING(256) NOT NULL,
  source_id STRING(128)
) PRIMARY KEY (edge_id);

CREATE TABLE InstrumentControlEdges (
  edge_id STRING(128) NOT NULL,
  instrument_entity_id STRING(256) NOT NULL,
  target_entity_id STRING(256) NOT NULL,
  loop_id STRING(128) NOT NULL,
  instrument_type STRING(256),
  setpoint_or_range STRING(256),
  interlock_or_alarm STRING(512),
  source_concept_id STRING(256) NOT NULL,
  source_id STRING(128)
) PRIMARY KEY (edge_id);

CREATE TABLE ConceptWikiLinks (
  edge_id STRING(128) NOT NULL,
  from_concept_id STRING(256) NOT NULL,
  to_concept_id STRING(256) NOT NULL,
  section_heading STRING(256)
) PRIMARY KEY (edge_id);

CREATE TABLE FactLineageEdges (
  lineage_id STRING(128) NOT NULL,
  fact_id STRING(128) NOT NULL,
  concept_id STRING(256) NOT NULL,
  source_id STRING(128) NOT NULL,
  raw_citation_string STRING(512) NOT NULL,
  source_role STRING(64) NOT NULL,
  bundle_version STRING(64) NOT NULL,
  extracted_at TIMESTAMP NOT NULL OPTIONS (allow_commit_timestamp=true)
) PRIMARY KEY (lineage_id);

CREATE INDEX idx_fact_lineage_by_source ON FactLineageEdges(source_id, concept_id);

CREATE INDEX idx_fact_lineage_by_concept ON FactLineageEdges(concept_id, source_id);

CREATE OR REPLACE PROPERTY GRAPH OkfKnowledgeGraph
  NODE TABLES (
    EngineeringEntities AS Entity
      KEY (entity_id)
      LABEL Entity PROPERTIES (entity_id, entity_type, canonical_tag, name, equipment_class, unit, concept_id),
    OkfConcepts AS Concept
      KEY (concept_id)
      LABEL Concept PROPERTIES (concept_id, category, name, description, unit, trust_tier, has_conflict, conflict_count, gcs_uri),
    FactAssertions AS Fact
      KEY (fact_id)
      LABEL Fact PROPERTIES (fact_id, concept_id, entity_id, section_heading, parameter_name, parameter_value, parameter_unit, has_conflict, conflict_note),
    RawSourceDocuments AS RawDocument
      KEY (source_id)
      LABEL RawDocument PROPERTIES (source_id, filename, subfolder, doc_code, revision, md5_hash, gcs_uri)
  )
  EDGE TABLES (
    ProcessConnections AS CONNECTS_TO
      KEY (edge_id)
      SOURCE KEY (from_entity_id) REFERENCES Entity (entity_id)
      DESTINATION KEY (to_entity_id) REFERENCES Entity (entity_id)
      LABEL CONNECTS_TO PROPERTIES (stream_or_line_id, fluid_service, temperature, pressure, flow_rate, source_concept_id, source_id),
    InstrumentControlEdges AS MONITORS_OR_TRIPS
      KEY (edge_id)
      SOURCE KEY (instrument_entity_id) REFERENCES Entity (entity_id)
      DESTINATION KEY (target_entity_id) REFERENCES Entity (entity_id)
      LABEL MONITORS_OR_TRIPS PROPERTIES (loop_id, instrument_type, setpoint_or_range, interlock_or_alarm, source_concept_id, source_id),
    ConceptWikiLinks AS LINKS_TO_CONCEPT
      KEY (edge_id)
      SOURCE KEY (from_concept_id) REFERENCES Concept (concept_id)
      DESTINATION KEY (to_concept_id) REFERENCES Concept (concept_id)
      LABEL LINKS_TO_CONCEPT PROPERTIES (section_heading),
    FactLineageEdges AS DERIVED_FROM
      KEY (lineage_id)
      SOURCE KEY (fact_id) REFERENCES Fact (fact_id)
      DESTINATION KEY (source_id) REFERENCES RawDocument (source_id)
      LABEL DERIVED_FROM PROPERTIES (concept_id, raw_citation_string, source_role, bundle_version)
  );
