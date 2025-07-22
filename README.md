# Arthistorical Semantic Data Extraction

A comprehensive pipeline designed to extract semantic triplets from arthistorical texts using advanced natural language processing and knowledge graph alignment techniques. This project bridges the gap between unstructured art historical texts and structured semantic data, enabling researchers to discover relationships and patterns in art historical knowledge.

## Overview

This pipeline processes arthistorical texts to extract meaningful semantic relationships in the form of triplets (subject-predicate-object), which are then aligned with Wikidata entities to ensure consistency and interoperability with existing knowledge graphs.

## Features

- **Multi-model LLM support**: Leverage different language models for text parsing and entity extraction
- **Wikidata alignment**: Automatically align extracted entities with Wikidata entries
- **Human-in-the-loop validation**: Export results to CSV for manual review and correction
- **Flexible input formats**: Support for various text formats and sources
- **Semantic triplet extraction**: Extract relationships between artworks, artists, movements, and historical contexts

## Pipeline Architecture

The pipeline consists of three main stages:

### 1. Text Parsing with LLM Models

- **Input**: Raw arthistorical texts (books, articles, exhibition catalogs)
- **Process**: Natural language processing using configurable LLM models
- **Output**: Structured entities and relationships
- **Supported Models**:
  - GPT-3.5/GPT-4 (OpenAI)
  - Claude (Anthropic)
  - Local models via Ollama
  - Custom fine-tuned models

### 2. Wikidata Alignment

- **Input**: Extracted entities from stage 1
- **Process**: Entity linking and disambiguation using Wikidata API
- **Output**: Aligned semantic triplets with Wikidata QIDs
- **Features**:
  - Fuzzy matching for entity names
  - Confidence scoring for alignments
  - Fallback strategies for unmatched entities

### 3. Export and Validation

- **Input**: Aligned semantic triplets
- **Process**: Format results for human review
- **Output**: CSV files with validation columns
- **Features**:
  - Confidence scores for each triplet
  - Source text references
  - Validation status tracking

### Sample Output

The pipeline generates CSV files with the following structure (later a snippet of the text source will be included here):

| text1 | text1_link | text2 | text2_link | text3 | text3_link |
|---------|-----------|---------|-------------|---------------|------------|
| Gut Altenkamp | <https://www.wikidata.org/wiki/Q668492> | commissioned by | <https://www.wikidata.org/wiki/Property:P88> | Hermann Anton Bernhard von Velen | <https://www.wikidata.org/wiki/Q61658390> |
| Gut Altenkamp | <https://www.wikidata.org/wiki/Q668492> | street address | <https://www.wikidata.org/wiki/Property:P6375> | Am Altenkamp 1, 26871 Papenburg | |
