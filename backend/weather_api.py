"""Project-scoped weather workspace; review remains an explicit evidence action."""
from fastapi.responses import Response

from .weather import Weather, EPWAnalysis, NASARequest, SOURCES


def register_weather(app, domain):
    domain.weather = app.state.weather = weather = Weather(domain)

    @app.get("/api/projects/{project_id}/weather/sources")
    def sources(project_id: str):
        return SOURCES

    @app.get("/api/projects/{project_id}/weather")
    def history(project_id: str):
        return weather.list(project_id)

    @app.post("/api/projects/{project_id}/weather/epw", status_code=201)
    def epw(project_id: str, body: EPWAnalysis):
        return weather.epw(project_id, body)

    @app.post("/api/projects/{project_id}/weather/nasa", status_code=201)
    def nasa(project_id: str, body: NASARequest):
        return weather.nasa(project_id, body)

    @app.get("/api/projects/{project_id}/weather/{weather_id}")
    def detail(project_id: str, weather_id: str):
        return weather.get(project_id, weather_id)

    @app.get("/api/projects/{project_id}/weather/{weather_id}/data.csv")
    def export_csv(project_id: str, weather_id: str):
        return Response(weather.csv(project_id, weather_id), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{weather_id}.csv"'})
