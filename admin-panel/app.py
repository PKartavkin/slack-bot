from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import os
import sys
import json

# Add parent directory to path to import bot modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from bot.db import orgs

app = FastAPI()

# Determine paths for static files and templates
admin_panel_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(admin_panel_dir, "static")
templates_dir = os.path.join(admin_panel_dir, "templates")

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates = Jinja2Templates(directory=templates_dir)

# Add tojson filter to Jinja2
templates.env.filters["tojson"] = json.dumps

# Basic auth
security = HTTPBasic()

# Admin credentials (hardcoded for now as per requirements)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin"


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify admin credentials"""
    if credentials.username != ADMIN_USERNAME or credentials.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def format_date(date_str: str) -> str:
    """Format ISO date string to date only (without time)"""
    try:
        if isinstance(date_str, str):
            # Parse ISO format with or without Z
            if date_str.endswith('Z'):
                date_str = date_str[:-1]
            dt = datetime.fromisoformat(date_str)
            return dt.strftime("%Y-%m-%d")
        return "N/A"
    except Exception:
        return "N/A"


def get_org_stats(team_id: str) -> dict:
    """Get organization statistics"""
    try:
        org = orgs.find_one({"team_id": team_id})
        if not org:
            return {
                "client_id": team_id,
                "date_joined": "N/A",
                "num_channels": 0,
                "num_projects": 0,
                "num_bot_invocations": 0,
                "project_descriptions": {}
            }
        
        # Count channels
        channel_projects = org.get("channel_projects", {})
        num_channels = len(channel_projects) if channel_projects else 0
        
        # Count projects
        projects = org.get("projects", {})
        num_projects = len(projects) if projects else 0
        
        # Get bot invocations
        num_bot_invocations = org.get("bot_invocations_total", 0)
        
        # Get joined date
        joined_date = org.get("joined_date", "")
        date_joined = format_date(joined_date) if joined_date else "N/A"
        
        # Get project descriptions (project_context from each project)
        project_descriptions = {}
        if projects:
            for project_name, project_data in projects.items():
                project_context = project_data.get("project_context", "").strip()
                if project_context:
                    project_descriptions[project_name] = project_context
        
        return {
            "client_id": team_id,
            "date_joined": date_joined,
            "num_channels": num_channels,
            "num_projects": num_projects,
            "num_bot_invocations": num_bot_invocations,
            "project_descriptions": project_descriptions
        }
    except Exception as e:
        # Return default stats on error
        return {
            "client_id": team_id,
            "date_joined": "N/A",
            "num_channels": 0,
            "num_projects": 0,
            "num_bot_invocations": 0,
            "project_descriptions": {}
        }


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, username: str = Depends(verify_admin)):
    """Main admin panel page"""
    # Get all organizations
    try:
        all_orgs = list(orgs.find({}, {"team_id": 1}))
        orgs_list = []
        
        for org in all_orgs:
            team_id = org.get("team_id")
            if team_id:
                stats = get_org_stats(team_id)
                orgs_list.append(stats)
        
        # Sort by client_id
        orgs_list.sort(key=lambda x: x["client_id"])
        
    except Exception as e:
        orgs_list = []
    
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "orgs": orgs_list}
    )


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}
