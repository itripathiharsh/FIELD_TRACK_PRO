# FieldTrack Pro Admin Dashboard (`fieldtrackpro-web`)

React 18 / Vite / TypeScript admin web application for FieldTrack Pro.

## Stack

| Concern | Dependency |
|---|---|
| UI Framework | React 18 |
| Build Tool | Vite 5 |
| Language | TypeScript 5.6 |
| Styling | Tailwind CSS 3 |
| Icons | Lucide React |

## Prerequisites

- Node.js 20+
- npm 10+

## Setup

```bash
# 1. Install dependencies
npm install

# 2. Copy environment config
cp .env.example .env

# 3. Start development server
npm run dev
```

App runs at: `http://localhost:5173`

## Build

```bash
npm run build
```

## Environment Variables

| Variable | Description |
|---|---|
| `VITE_API_BASE_URL` | FastAPI backend base URL (default: `http://localhost:8000/api/v1`) |
| `VITE_APP_ENV` | App environment label (default: `development`) |
