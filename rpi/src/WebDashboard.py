import threading
import uvicorn
import pathlib
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

class WebDashboard(threading.Thread):
    def __init__(self, config_manager, data_manager, logger, host="0.0.0.0", port=8080):
        super().__init__(daemon=True, name="WebDashboard")
        self.config_manager = config_manager
        self.data_manager = data_manager
        self.logger = logger
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
            return self.templates.TemplateResponse(request=request, name="node_index.html", context={})

        @self.app.get("/api/status")
        async def status():
            node_id = self.config_manager.get("node_id", "node1")
            
            # 1. Gather Alert History
            recent_alerts = []
            try:
                # The alert file is in EdgeNode/logs/events.log or rpi/src/alerts/alerts.jsonl
                # AlertManager writes to the alerts directory
                alerts_path = pathlib.Path("alerts/alerts.jsonl")
                if alerts_path.exists():
                    with open(alerts_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        for line in reversed(lines[-20:]):
                            import json
                            recent_alerts.append(json.loads(line.strip()))
            except Exception:
                pass

            # 2. Extract live inference telemetry
            inference_data = {}
            alert_count = 0
            if hasattr(self.data_manager, "inference_engine"):
                inference_data = getattr(self.data_manager.inference_engine, "last_inference_data", {})
            if hasattr(self.data_manager, "alert_manager"):
                alert_count = getattr(self.data_manager.alert_manager, "alert_count", 0)

            # 3. Performance Metrics
            cpu_usage = "N/A"
            mem_usage = "N/A"
            mem_free = "N/A"
            try:
                import psutil
                cpu_usage = f"{psutil.cpu_percent()}%"
                mem = psutil.virtual_memory()
                mem_usage = f"{mem.percent}%"
                mem_free = f"{mem.available / (1024*1024):.0f} MB"
            except ImportError:
                pass

            return {
                "node_id": node_id,
                "status": "Online",
                "alert_count": alert_count,
                "recent_alerts": recent_alerts,
                "inference_data": inference_data,
                "performance": {
                    "cpu_usage": cpu_usage,
                    "mem_usage": mem_usage,
                    "mem_free": mem_free
                }
            }

    def run(self):
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        server = uvicorn.Server(config)
        server.run()
