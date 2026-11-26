from django.http import HttpResponse

HEALTH_PATH = "/healthz"


class HealthCheckMiddleware:
    """Answer the container health check before any other middleware.

    It runs ahead of host validation (CommonMiddleware), sessions and auth,
    so `http://localhost:8000/healthz` works whatever ALLOWED_HOSTS is. It
    reveals nothing: the process is up and serving requests.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == HEALTH_PATH:
            return HttpResponse(b"ok", content_type="text/plain")
        return self.get_response(request)
