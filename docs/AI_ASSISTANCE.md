# AI Assistance in Development

This document acknowledges the AI tools and resources used during the development of Kalissa Topic Modelling. AI assistance was instrumental in accelerating development, exploring architectural decisions, and solving complex problems.

## AI Tools Used

### 1. Cursor AI

**Primary Use**: Integrated development environment with AI-powered code generation and assistance.

**Contributions**:

#### Initial Project Setup
- **Flask Application Structure**: Generated initial project structure with proper separation of concerns (routes, services, models, tasks)
- **Docker Configuration**: Created `docker-compose.yml` with multi-service setup (web, worker, db, redis)
- **Database Models**: Generated SQLAlchemy models with proper relationships and pgvector integration
- **Celery Configuration**: Set up Celery app with proper broker/backend configuration
- **Environment Configuration**: Created config management with environment variable handling

#### Test Suite Development
- **Test Fixtures**: Generated pytest fixtures for database sessions, test collections, and mock data
- **Unit Tests**: Created comprehensive test suite covering:
  - API route testing (`test_api_routes.py`)
  - Service layer testing (`test_services_*.py`)
  - Celery task testing (`test_tasks.py`)
  - Database model testing (`test_models.py`)
- **Test Utilities**: Generated helper functions for creating test documents, collections, and topics
- **Mocking**: Set up mocks for OpenAI API calls and external dependencies

#### Documentation Generation
- **README.md**: Initial structure and setup instructions
- **Code Comments**: Generated docstrings for functions and classes
- **Type Hints**: Added type annotations throughout the codebase
- **API Documentation**: Structured endpoint documentation

#### Debugging and Issue Resolution
- **Error Analysis**: Helped identify and fix:
  - Celery task serialization problems
  - Embedding dimension mismatches
  - Citation parsing edge cases
- **Performance Issues**: Identified bottlenecks in embedding generation and clustering
- **Transaction Management**: Resolved database transaction and session management issues

**Key Features Leveraged**:
- Inline code suggestions and completions
- Chat-based code explanation and refactoring
- Multi-file context understanding
- Error message interpretation and fixes

### 2. GPT-5 (ChatGPT) and Google Gemini (Web Interface)

**Primary Use**: Research, architectural decision-making, and algorithm exploration.

**Contributions**:

#### Topic Modeling Approach Research

**Investigated Approaches**:

1. **K-means Clustering**
   - **Pros**: Fast, deterministic, scalable, simple to implement
   - **Cons**: Requires pre-specifying k, assumes spherical clusters
   - **Decision**: Selected for production use
   - **Rationale**: Best balance of speed, simplicity, and quality for document embeddings

2. **Hierarchical Clustering**
   - **Pros**: No need to specify k, creates dendrogram for visualization
   - **Cons**: O(n²) or O(n² log n) complexity, too slow for large datasets
   - **Decision**: Rejected due to scalability concerns
   - **Alternative Considered**: Agglomerative clustering with Ward linkage

3. **DBSCAN**
   - **Pros**: Handles non-spherical clusters, identifies outliers
   - **Cons**: Requires tuning epsilon and min_samples, unpredictable topic count
   - **Decision**: Rejected for production
   - **Use Case**: Considered for outlier detection in future iterations

4. **Latent Dirichlet Allocation (LDA)**
   - **Pros**: Probabilistic, interpretable topic distributions
   - **Cons**: Requires pre-specifying number of topics, slower convergence, works on word counts not embeddings
   - **Decision**: Rejected
   - **Note**: Better suited for traditional NLP, not embedding-based approaches

5. **HDBSCAN (Hierarchical DBSCAN)**
   - **Pros**: Variable number of clusters, handles noise
   - **Cons**: More complex, harder to tune, less deterministic
   - **Decision**: Rejected for initial version
   - **Future Consideration**: May revisit for incremental updates

6. **Gaussian Mixture Models (GMM)**
   - **Pros**: Soft clustering, probabilistic assignments
   - **Cons**: Slower than K-means, assumes Gaussian distributions
   - **Decision**: Rejected
   - **Note**: Overkill for this use case

#### Embedding Strategy Research

**Explored Options**:

1. **Document-Level Embeddings**
   - **Pros**: Simpler, fewer API calls
   - **Cons**: Poor clustering for multi-topic documents, loses granularity
   - **Decision**: Rejected
   - **GPT Insight**: "Documents often span multiple topics. Chunk-level embeddings provide better semantic granularity."

2. **Chunk-Level Embeddings**
   - **Pros**: Better clustering, documents can belong to multiple topics, more accurate
   - **Cons**: More API calls, more storage
   - **Decision**: Selected
   - **GPT Insight**: "800-1200 token chunks with 100-200 token overlap maintain context while providing focused semantic units."

3. **Sentence-Level Embeddings**
   - **Pros**: Very granular
   - **Cons**: Too many chunks, context loss, expensive
   - **Decision**: Rejected
   - **Note**: Considered for future fine-grained analysis

#### Clustering Parameter Selection

**K Selection Formula Research**:
- **Explored**: `k = sqrt(n/2)`, `k = n/10`, `k = log(n)`, Elbow method
- **Selected**: `k = sqrt(n/2)`
- **GPT Rationale**: "Provides a reasonable number of topics that scales with data size without over-clustering. The square root relationship prevents exponential growth while ensuring sufficient granularity."

#### Relationship Building Strategy

**Similarity Metrics Explored**:
- **Cosine Similarity**: Selected (magnitude-invariant, semantic focus)
- **Euclidean Distance**: Rejected (sensitive to magnitude)
- **Manhattan Distance**: Rejected (less suitable for high-dimensional spaces)
- **Pearson Correlation**: Rejected (overkill for this use case)

**Threshold Selection**:
- **Explored**: 0.15, 0.20, 0.25, 0.30, 0.35
- **Selected**: 0.25
- **GPT Insight**: "0.25 captures meaningful relationships without creating noise. Lower thresholds create too many edges, higher thresholds miss important connections."
