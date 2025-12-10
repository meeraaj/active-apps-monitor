# 🖥️ Active Apps Monitor

**Active Apps Monitor** is a productivity-focused application that monitors laptop app usage, builds structured usage logs, and prepares the data for machine learning–based productivity classification.

The project helps users understand how their time is distributed across applications and enables flagging of productive and non-productive activity.

---

## 🚀 Features

- 📡 Monitors active (foreground) applications on a laptop  
- ⏱️ Builds usage sessions with start time, end time, and duration  
- 📂 Stores usage logs locally in CSV / JSON format  
- 🧠 Prepares data for ML-based productivity flagging  
- 📊 Generates usage summaries and statistics  
- 🔌 Easily extendable for dashboards and real-time analysis  

---

## 🏗️ System Architecture

```mermaid
flowchart LR
  classDef source fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1;
  classDef core fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20;
  classDef storage fill:#FFF3E0,stroke:#EF6C00,stroke-width:2px,color:#E65100;
  classDef output fill:#F3E5F5,stroke:#6A1B9A,stroke-width:2px,color:#4A148C;
  classDef config fill:#EDE7F6,stroke:#3949AB,stroke-width:2px,color:#1A237E;

  OS(["Operating System<br/>(Windows / macOS / Linux)"]):::source
  Config[["Configuration & Rules<br/>(Productivity labels)"]]:::config

  subgraph Core["Active Apps Monitor Core"]
    Monitor["Foreground App Monitor<br/>(Window & Process Tracker)"]:::core
    Sessionizer["Session Builder<br/>(Start • End • Duration)"]:::core
  end

  subgraph Storage["Local Storage"]
    Logs[["Usage Logs<br/>(CSV / JSON File DB)"]]:::storage
  end

  subgraph Output["Outputs & Integrations"]
    CLI["CLI Summary & Stats"]:::output
    Export["Export for ML Analysis<br/>(Notebooks / Dashboards)"]:::output
  end

  OS --> Monitor
  Config --> Monitor
  Monitor --> Sessionizer
  Sessionizer --> Logs
  Logs --> CLI
  Logs --> Export
