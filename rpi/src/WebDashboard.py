import threading
import uvicorn
import pathlib
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

class WebDashboard(threading.Thread):
    def __init__(self, config_manager, data_manager, alert_manager, host="0.0.0.0", port=8080):
        super().__init__(daemon=True, name="WebDashboard")
        self.config_manager = config_manager
        self.data_manager = data_manager
        self.alert_manager = alert_manager
        self.host = host
        self.port = port
        
        self.app = FastAPI(title="Edge Node Dashboard")
        
        # Setup templates
        self.templates_dir = pathlib.Path(__file__).parent / "templates"
        self.templates_dir.mkdir(exist_ok=True)
        self.templates = Jinja2Templates(directory=str(self.templates_dir))
        
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            return self.templates.TemplateResponse("node_index.html", {"request": request})

        @self.app.get("/api/status")
        async def status():
            node_id = self.config_manager.get("node_id", "Unknown")
            
            # Read the last few alerts from alerts.jsonl if it exists
            recent_alerts = []
            try:
                alerts_path = pathlib.Path("alerts/alerts.jsonl")
                if alerts_path.exists():
                    with open(alerts_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        # Get last 5 alerts
                        for line in reversed(lines[-5:]):
                            import json
                            recent_alerts.append(json.loads(line))
            except Exception:
                pass

            return {
                "node_id": node_id,
                "status": "Online",
                "alert_count": getattr(self.alert_manager, "alert_count", 0) if self.alert_manager else 0,
                "recent_alerts": recent_alerts
            }

    def run(self):
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        server = uvicorn.Server(config)
        server.run()
