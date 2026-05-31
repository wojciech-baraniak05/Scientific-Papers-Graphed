from __future__ import annotations

import random

from locust import HttpUser, between, task


class ApiUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.paper_ids: list[str] = []
        self.field_ids: list[str] = []
        resp = self.client.get("/api/papers/search", params={"limit": 50})
        if resp.status_code == 200:
            self.paper_ids = [p["id"] for p in resp.json()]
        fields = self.client.get("/api/fields")
        if fields.status_code == 200:
            self.field_ids = [f["id"] for f in fields.json().get("fields", [])]

    @task(1)
    def health(self) -> None:
        self.client.get("/api/health")

    @task(2)
    def fields(self) -> None:
        self.client.get("/api/fields")

    @task(4)
    def search(self) -> None:
        self.client.get("/api/papers/search", params={"q": "learning", "limit": 20})

    @task(4)
    def graph(self) -> None:
        if not self.paper_ids:
            return
        pid = random.choice(self.paper_ids)
        direction = random.choice(["cites", "cited_by"])
        self.client.get(
            f"/api/papers/{pid}/graph",
            params={"direction": direction, "limit": 50},
            name="/api/papers/[id]/graph",
        )

    @task(3)
    def ranking(self) -> None:
        if not self.field_ids:
            return
        fid = random.choice(self.field_ids)
        order_by = random.choice(["papers", "papers_per_gdp", "papers_per_university"])
        self.client.get(
            f"/api/fields/{fid}/country-ranking",
            params={"order_by": order_by, "limit": 30},
            name="/api/fields/[id]/country-ranking",
        )
