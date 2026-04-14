# Conjunx — Conjunction Analysis Engine

Conjunx is a **satellite conjunction analysis and collision avoidance decision engine** that ingests live Conjunction Data Messages (CDMs) from the US Space Force's 18th Space Defense Squadron via Space-Track, independently verifies collision probability using orbital mechanics, and provides actionable maneuver recommendations — all through a mission-control-grade web interface with 3D orbital visualization.

## 🚀 Features

- **Live Data Ingestion**: Live CDMs from Space-Track, TLE fetching + caching, and SATCAT metadata lookup.
- **Orbital Analysis**: SGP4 propagation to TCA, conjunction plane projection, Foster Pc computation, anisotropic covariance modeling, and independent verification vs 18th SDS.
- **Risk Assessment**: 4-axis scoring (Pc, miss, maneuverability, urgency) with CRITICAL/HIGH/MEDIUM/LOW labels and debris detection.
- **Maneuver Planning**: Along-track ΔV solver, Tsiolkovsky fuel estimation, Pc re-estimation post-maneuver, and an interactive tradeoff slider.
- **Sensitivity Analysis**: 12-point covariance sweep and interactive Pc vs uncertainty graph.
- **3D Visualization**: CesiumJS 3D globe with animated orbit tracks, TCA marker, miss-distance line, covariance ellipsoids, and close-approach auto-zoom.
- **AI Explainability**: LLM-generated situation briefs, risk rationale, and maneuver recommendations.

### What Conjunx Covers Today

```mermaid
mindmap
  root((Conjunx))
    Data Ingestion
      Live CDMs from Space-Track
      TLE fetching + caching
      SATCAT metadata lookup
      CDM grouping by pair
    Orbital Analysis
      SGP4 propagation to TCA
      Conjunction plane projection
      Foster Pc computation
      Anisotropic covariance model
      Independent verification vs 18th SDS
    Risk Assessment
      4-axis scoring (Pc, miss, maneuverability, urgency)
      CRITICAL/HIGH/MEDIUM/LOW labels
      Debris detection
      Recommended actions
    Maneuver Planning
      Along-track ΔV solver
      Tsiolkovsky fuel estimation
      Pc re-estimation post-maneuver
      Interactive tradeoff slider
      Ghost orbit visualization
    Sensitivity Analysis
      12-point covariance sweep
      Interactive Pc vs uncertainty graph
      Explainability notes
    Visualization
      CesiumJS 3D globe
      Animated orbit tracks
      TCA marker + miss distance line
      Covariance ellipsoids
      Close-approach auto-zoom
      Pc maturation timeline
    AI Layer
      LLM situation briefs
      Risk rationale
      Maneuver recommendations
      No-action scenarios
```

## ⚙️ System Architecture

```mermaid
graph TB
    subgraph External["🌐 External Data Sources"]
        ST["Space-Track API<br/>(18th SDS)"]
    end

    subgraph Backend["⚙️ Python Backend (FastAPI)"]
        FETCH["data/fetcher.py<br/>SpaceTrackFetcher"]
        PROC["engine/processor.py<br/>Pipeline Orchestrator"]
        PC["engine/pc_calculator.py<br/>Foster Pc Engine"]
        MAN["engine/maneuver.py<br/>Avoidance Solver"]
        PROP["engine/propagator.py<br/>SGP4 Propagator"]
        RISK["engine/risk_scorer.py<br/>4-Axis Risk Scorer"]
        AI["ai/explainer.py<br/>LLM Explainer"]
        CACHE[("cache.db<br/>SQLite")]
    end

    subgraph API["🔌 REST API Layer"]
        R1["GET /conjunctions"]
        R2["GET /conjunctions/:id"]
        R3["GET /.../pc-analysis"]
        R4["POST /.../maneuver"]
        R5["POST /.../tradeoff"]
        R6["GET /.../orbit-data"]
    end

    subgraph Frontend["🖥️ Next.js Frontend"]
        LIST["ConjunctionList"]
        DETAIL["Detail Page"]
        CESIUM["CesiumViewer<br/>3D Globe"]
        PCV["PcVerificationPanel"]
        SENS["PcSensitivityChart"]
        MPAN["ManeuverPanel"]
        TRADE["ManeuverTradeoff"]
        AIUI["AIExplainer"]
        PCEVO["PcEvolutionChart"]
    end

    ST -->|CDMs, TLEs, SATCAT| FETCH
    FETCH --> CACHE
    CACHE --> PROC
    PROC --> PC
    PROC --> MAN
    PROC --> PROP
    PROC --> RISK
    PROC --> AI
    PROC --> AI

    PROC --> R1 & R2 & R3 & R4 & R5
    PROP --> R6

    R1 --> LIST
    R2 --> DETAIL
    R3 --> PCV
    R3 --> SENS
    R4 --> MPAN
    R5 --> TRADE
    R6 --> CESIUM
    AI --> AIUI
```

### Python Backend (FastAPI)
The backend acts as an independent verification engine:
- `data/fetcher.py`: Space-Track API client with SQLite caching.
- `engine/processor.py`: Pipeline orchestrator.
- `engine/pc_calculator.py`: Foster & Estes (1992) Pc engine.
- `engine/maneuver.py`: Avoidance maneuver solver.
- `engine/propagator.py`: SGP4 orbit propagation.
- `engine/risk_scorer.py`: 4-axis risk scoring.
- `ai/explainer.py`: LLM-powered context and recommendations.

### Next.js Frontend
Mission-control UI built with React, CesiumJS, and Tailwind CSS.
Provides a 60/40 split layout mapping a 3D globe to analysis panels including an interactive Maneuver Tradeoff slider, Pc Sensitivity charts, and historical Pc Maturation tracking.

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Orbit Mechanics | SGP4 (`sgp4`), SciPy (numerical integration) |
| Data Source | Space-Track REST API (18th SDS) |
| Caching | SQLite |
| Frontend | Next.js 16, React 19, TypeScript |
| 3D Visualization | CesiumJS (WebGL globe) |
| Charts | Raw HTML5 Canvas |
| Styling | Tailwind CSS (dark mission-control theme) |

## 📦 File Structure

```
Conjunx/
├── api/             # FastAPI routes
├── ai/              # LLM situation briefs
├── data/            # Space-Track client + SQLite cache
├── engine/          # Math: Pc solver, propagator, maneuver solver
├── frontend/        # Next.js web application
│   ├── src/app/
│   ├── src/components/
│   └── src/lib/
├── run.py           # Backend server entry point
└── requirements.txt # Python dependencies
```

## 🧠 Data Pipeline

```mermaid
sequenceDiagram
    participant ST as Space-Track
    participant F as Fetcher
    participant P as Processor
    participant SGP4 as SGP4 Engine
    participant PC as Foster Pc
    participant M as Maneuver Solver
    participant RS as Risk Scorer
    participant AI as LLM Explainer
    participant UI as Frontend

    F->>ST: Fetch CDMs (cdm_public)
    ST-->>F: CDM array (TCA, Pc, miss distance...)
    F->>ST: Fetch TLEs (NORAD IDs)
    ST-->>F: TLE line1/line2
    F->>ST: Fetch SATCAT metadata
    ST-->>F: Object type, RCS size, country...

    Note over P: Pipeline Start

    P->>SGP4: Propagate TLE₁ to TCA
    SGP4-->>P: State vector (pos, vel) @ TCA
    P->>SGP4: Propagate TLE₂ to TCA
    SGP4-->>P: State vector (pos, vel) @ TCA

    P->>PC: Compute conjunction geometry
    PC->>PC: Project covariance → 2D plane
    PC->>PC: Foster integration (Gaussian over HBR disk)
    PC->>PC: Sensitivity sweep (12 scale factors)
    PC-->>P: PcResult (Pc, notes, risk, sensitivity curve)

    P->>M: Solve avoidance maneuver
    M->>M: ΔV from miss-distance gap
    M->>M: Tsiolkovsky fuel cost
    M->>M: Pc re-estimation post-burn
    M-->>P: ManeuverSolution

    P->>RS: Score on 4 axes
    RS-->>P: RiskAssessment (score, level, action)

    P->>AI: Generate explanation
    AI-->>P: Natural language brief

    P-->>UI: Combined JSON response
```

1. **Fetch**: Ingests CDMs, TLEs, and SATCAT from Space-Track.
2. **Propagate**: Uses SGP4 to propagate both satellites' TLEs to Time of Closest Approach (TCA).
3. **Analyze geometry**: Computes the miss vector and projects it onto the 2D conjunction plane.
4. **Compute Pc**: Integrates a 2D Gaussian over the hard-body collision cross-section (Foster's method).
5. **Solve maneuver**: Calculates the required ΔV to double the miss distance (min 1 km) using an along-track burn.
6. **Score & Explain**: Scores the risk on 4 axes and asks an LLM to generate an operator brief.
7. **Visualize**: Pre-computes 95-minute ECEF orbit tracks for CesiumJS rendering.
