package com.boardsight.web.api;

import com.boardsight.service.PipelineRunResult;
import com.boardsight.service.PythonPipelineRunner;
import com.boardsight.web.data.MeetingRepository;
import com.boardsight.web.http.HttpUtils;
import com.boardsight.web.http.MultipartFormData;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;

public final class ApiHandlers {
    private ApiHandlers() {
    }

    public static void register(HttpServer server, Path projectRoot) {
        MeetingRepository repository = new MeetingRepository(projectRoot.resolve("output"));
        server.createContext("/api/health", exchange -> HttpUtils.sendJson(exchange, 200, "{\"status\":\"ok\"}"));
        server.createContext("/api/auth/login", new AuthProxyHandler("/api/v1/auth/login"));
        server.createContext("/api/auth/register", new AuthProxyHandler("/api/v1/auth/register"));
        server.createContext("/api/auth/me", new MeHandler());
        server.createContext("/api/meetings", new MeetingsHandler(repository));
        server.createContext("/api/meeting", new MeetingDetailHandler(repository));
        server.createContext("/api/reports", new ReportHandler(repository));
        server.createContext("/api/analyze", new AnalyzeHandler(projectRoot, repository));
        server.createContext("/api/live", new LiveHandler());
        server.createContext("/", new StaticHandler());
    }

    private static final class AuthProxyHandler implements HttpHandler {
        private final String targetPath;

        private AuthProxyHandler(String targetPath) {
            this.targetPath = targetPath;
        }

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "POST");
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl == null) {
                HttpUtils.sendJson(exchange, 503, "{\"error\":\"Authentication backend is unavailable.\"}");
                return;
            }

            byte[] requestBody = exchange.getRequestBody().readAllBytes();
            String query = exchange.getRequestURI().getRawQuery();
            String targetUrl = aiServiceUrl + targetPath + (query == null || query.isBlank() ? "" : "?" + query);
            HttpResponse<byte[]> response;
            try {
                response = sendJsonRequest(
                    targetUrl,
                    "POST",
                    requestBody,
                    exchange.getRequestHeaders().getFirst("Authorization")
                );
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Authentication request was interrupted.", exception);
            }
            HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), "application/json; charset=utf-8");
        }
    }

    private static final class LiveHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl == null) {
                HttpUtils.sendJson(exchange, 503, "{\"error\":\"Live copilot requires the AI service to be connected.\"}");
                return;
            }

            String path = exchange.getRequestURI().getPath();
            String method = exchange.getRequestMethod().toUpperCase();
            String targetUrl;

            if ("/api/live/start".equals(path) && "POST".equals(method)) {
                targetUrl = aiServiceUrl + "/api/v1/live/start";
            } else if ("/api/live/active".equals(path) && "GET".equals(method)) {
                targetUrl = aiServiceUrl + "/api/v1/live/active";
            } else {
                String[] parts = path.split("/");
                if (parts.length < 4) {
                    HttpUtils.sendJson(exchange, 400, "{\"error\":\"Invalid live session route.\"}");
                    return;
                }
                String sessionId = parts[3];
                if (parts.length == 4 && "GET".equals(method)) {
                    targetUrl = aiServiceUrl + "/api/v1/live/" + URLEncoder.encode(sessionId, StandardCharsets.UTF_8);
                } else if (parts.length == 5 && "POST".equals(method)) {
                    String action = parts[4];
                    if (!action.equals("events") && !action.equals("copilot") && !action.equals("finalize")) {
                        HttpUtils.sendJson(exchange, 400, "{\"error\":\"Unsupported live session action.\"}");
                        return;
                    }
                    targetUrl = aiServiceUrl + "/api/v1/live/"
                        + URLEncoder.encode(sessionId, StandardCharsets.UTF_8)
                        + "/" + URLEncoder.encode(action, StandardCharsets.UTF_8);
                } else {
                    HttpUtils.sendJson(exchange, 405, "{\"error\":\"Method not allowed.\"}");
                    return;
                }
            }

            HttpResponse<byte[]> response;
            try {
                response = sendJsonRequest(
                    targetUrl,
                    method,
                    exchange.getRequestBody().readAllBytes(),
                    exchange.getRequestHeaders().getFirst("Authorization")
                );
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Live request to AI service was interrupted.", exception);
            }
            HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), "application/json; charset=utf-8");
        }
    }

    private static final class MeHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "GET");
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl == null) {
                HttpUtils.sendJson(exchange, 503, "{\"error\":\"Authentication backend is unavailable.\"}");
                return;
            }

            HttpResponse<byte[]> response;
            try {
                response = sendJsonRequest(
                    aiServiceUrl + "/api/v1/me",
                    "GET",
                    new byte[0],
                    exchange.getRequestHeaders().getFirst("Authorization")
                );
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Profile lookup was interrupted.", exception);
            }
            HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), "application/json; charset=utf-8");
        }
    }

    private static final class MeetingsHandler implements HttpHandler {
        private final MeetingRepository repository;

        private MeetingsHandler(MeetingRepository repository) {
            this.repository = repository;
        }

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "GET");
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl != null) {
                proxyJson(exchange, aiServiceUrl + "/api/v1/meetings");
                return;
            }
            HttpUtils.sendJson(exchange, 200, repository.listMeetingsJson());
        }
    }

    private static final class MeetingDetailHandler implements HttpHandler {
        private final MeetingRepository repository;

        private MeetingDetailHandler(MeetingRepository repository) {
            this.repository = repository;
        }

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "GET");
            Map<String, String> query = HttpUtils.parseQuery(exchange.getRequestURI().getRawQuery());
            String id = query.get("id");
            if (id == null || id.isBlank()) {
                HttpUtils.sendJson(exchange, 400, "{\"error\":\"Missing meeting id.\"}");
                return;
            }

            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl != null) {
                proxyJson(exchange, aiServiceUrl + "/api/v1/meetings/" + URLEncoder.encode(id, StandardCharsets.UTF_8));
                return;
            }

            String payload = repository.loadMeetingJson(id);
            if (payload == null) {
                HttpUtils.sendJson(exchange, 404, "{\"error\":\"Meeting not found.\"}");
                return;
            }
            HttpUtils.sendJson(exchange, 200, payload);
        }
    }

    private static final class ReportHandler implements HttpHandler {
        private final MeetingRepository repository;

        private ReportHandler(MeetingRepository repository) {
            this.repository = repository;
        }

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "GET");
            String[] parts = exchange.getRequestURI().getPath().split("/", 5);
            if (parts.length < 5) {
                HttpUtils.sendJson(exchange, 400, "{\"error\":\"Invalid report path.\"}");
                return;
            }

            String meetingId = parts[3];
            String fileName = parts[4];
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl != null) {
                proxyBinary(exchange, aiServiceUrl + "/api/v1/meetings/"
                    + URLEncoder.encode(meetingId, StandardCharsets.UTF_8)
                    + "/reports/"
                    + URLEncoder.encode(fileName, StandardCharsets.UTF_8), fileName);
                return;
            }

            Path reportPath = repository.resolveReport(meetingId, fileName);
            if (reportPath == null || !Files.exists(reportPath)) {
                HttpUtils.sendJson(exchange, 404, "{\"error\":\"Report not found.\"}");
                return;
            }
            HttpUtils.sendFile(exchange, 200, reportPath, HttpUtils.contentType(fileName));
        }
    }

    private static final class AnalyzeHandler implements HttpHandler {
        private final Path projectRoot;
        private final MeetingRepository repository;

        private AnalyzeHandler(Path projectRoot, MeetingRepository repository) {
            this.projectRoot = projectRoot;
            this.repository = repository;
        }

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "POST");
            String contentType = exchange.getRequestHeaders().getFirst("Content-Type");
            MultipartFormData upload = MultipartFormData.parse(exchange.getRequestBody(), contentType);
            if (upload == null || upload.fileName() == null || upload.bytes().length == 0) {
                HttpUtils.sendJson(exchange, 400, "{\"error\":\"Upload failed. Please choose a video file.\"}");
                return;
            }

            Path tempDir = projectRoot.resolve("output").resolve("uploads");
            Files.createDirectories(tempDir);
            String safeFileName = upload.fileName().replaceAll("[^a-zA-Z0-9._-]", "_");
            Path uploadPath = tempDir.resolve(Instant.now().toEpochMilli() + "-" + safeFileName);
            Files.write(uploadPath, upload.bytes());

            Path outputDir = projectRoot.resolve("output").resolve("web-run-" + Instant.now().toEpochMilli());
            try {
                PythonPipelineRunner runner = new PythonPipelineRunner(projectRoot, "python");
                String authorizationHeader = exchange.getRequestHeaders().getFirst("Authorization");
                Map<String, String> query = HttpUtils.parseQuery(exchange.getRequestURI().getRawQuery());
                Double startSeconds = parseOptionalDouble(query.get("start_seconds"));
                Double endSeconds = parseOptionalDouble(query.get("end_seconds"));
                String analysisProfile = query.get("analysis_profile");
                PipelineRunResult result = runner.run(uploadPath, outputDir, authorizationHeader, startSeconds, endSeconds, analysisProfile);
                String payload = Files.readString(result.resultJsonPath(), StandardCharsets.UTF_8);
                repository.refresh();
                HttpUtils.sendJson(exchange, 200, payload);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                HttpUtils.sendJson(exchange, 500, "{\"error\":\"Analysis was interrupted.\"}");
            } catch (Exception exception) {
                String message = exception.getMessage() == null ? "Analysis failed." : exception.getMessage();
                HttpUtils.sendJson(exchange, 500, "{\"error\":\"" + HttpUtils.escapeJson(message) + "\"}");
            } finally {
                Files.deleteIfExists(uploadPath);
            }
        }
    }

    private static Double parseOptionalDouble(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return Double.parseDouble(value);
    }

    private static final class StaticHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String requestPath = exchange.getRequestURI().getPath();
            String resourcePath = switch (requestPath) {
                case "/" -> "/public/index.html";
                case "/styles.css" -> "/public/styles.css";
                case "/app.js" -> "/public/app.js";
                default -> null;
            };

            if (resourcePath == null) {
                HttpUtils.sendJson(exchange, 404, "{\"error\":\"Not found.\"}");
                return;
            }

            byte[] bytes = HttpUtils.readResource(resourcePath);
            if (bytes == null) {
                HttpUtils.sendJson(exchange, 404, "{\"error\":\"Static asset not found.\"}");
                return;
            }
            HttpUtils.sendBytes(exchange, 200, bytes, HttpUtils.contentType(resourcePath));
        }
    }

    private static String aiServiceUrl() {
        String value = System.getenv("BOARDSIGHT_AI_URL");
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.replaceAll("/+$", "");
    }

    private static void proxyJson(HttpExchange exchange, String targetUrl) throws IOException {
        HttpResponse<byte[]> response;
        try {
            response = sendJsonRequest(
                targetUrl,
                exchange.getRequestMethod(),
                exchange.getRequestBody().readAllBytes(),
                exchange.getRequestHeaders().getFirst("Authorization")
            );
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("Request to AI service was interrupted.", exception);
        }
        HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), "application/json; charset=utf-8");
    }

    private static void proxyBinary(HttpExchange exchange, String targetUrl, String fileName) throws IOException {
        HttpResponse<byte[]> response;
        try {
            response = sendJsonRequest(
                targetUrl,
                exchange.getRequestMethod(),
                new byte[0],
                exchange.getRequestHeaders().getFirst("Authorization")
            );
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("Report request to AI service was interrupted.", exception);
        }
        HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), HttpUtils.contentType(fileName));
    }

    private static HttpResponse<byte[]> sendJsonRequest(
        String targetUrl,
        String method,
        byte[] body,
        String authorizationHeader
    ) throws IOException, InterruptedException {
        HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
            .uri(URI.create(targetUrl))
            .timeout(Duration.ofMinutes(5));

        if (authorizationHeader != null && !authorizationHeader.isBlank()) {
            requestBuilder.header("Authorization", authorizationHeader);
        }
        if (!"GET".equalsIgnoreCase(method)) {
            requestBuilder.header("Content-Type", "application/json");
        }

        if ("POST".equalsIgnoreCase(method)) {
            requestBuilder.POST(HttpRequest.BodyPublishers.ofByteArray(body));
        } else if ("GET".equalsIgnoreCase(method)) {
            requestBuilder.GET();
        } else {
            requestBuilder.method(method.toUpperCase(), HttpRequest.BodyPublishers.ofByteArray(body));
        }

        return HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build()
            .send(requestBuilder.build(), HttpResponse.BodyHandlers.ofByteArray());
    }
}
