package com.boardsight.web.api;

import com.boardsight.service.PipelineRunResult;
import com.boardsight.service.PythonPipelineRunner;
import com.boardsight.web.data.MeetingRepository;
import com.boardsight.web.http.HttpUtils;
import com.boardsight.web.http.MultipartFormData;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayInputStream;
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
        server.createContext("/api/live", new LiveProxyHandler(projectRoot));
        server.createContext("/api/gitlab", new GitLabProxyHandler());
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
                response = sendHttpRequest(
                    targetUrl,
                    "POST",
                    requestBody,
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    "application/json"
                );
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Authentication request was interrupted.", exception);
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
                response = sendHttpRequest(
                    aiServiceUrl + "/api/v1/me",
                    "GET",
                    new byte[0],
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    null
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
                PipelineRunResult result = runner.run(uploadPath, outputDir, authorizationHeader, startSeconds, endSeconds);
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

    private static final class LiveProxyHandler implements HttpHandler {
        private final Path projectRoot;

        private LiveProxyHandler(Path projectRoot) {
            this.projectRoot = projectRoot;
        }

        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl == null) {
                HttpUtils.sendJson(exchange, 503, "{\"error\":\"Live backend is unavailable.\"}");
                return;
            }

            String requestPath = exchange.getRequestURI().getPath();
            String suffix = requestPath.substring("/api/live".length());
            String targetPath;
            if (suffix.isBlank() || "/".equals(suffix)) {
                targetPath = "/api/v1/live";
            } else if ("/start".equals(suffix)) {
                targetPath = "/api/v1/live/start";
            } else {
                targetPath = "/api/v1/live" + suffix;
            }

            String query = exchange.getRequestURI().getRawQuery();
            String targetUrl = aiServiceUrl + targetPath + (query == null || query.isBlank() ? "" : "?" + query);
            String requestContentType = exchange.getRequestHeaders().getFirst("Content-Type");
            byte[] requestBody = exchange.getRequestBody().readAllBytes();
            String targetMethod = exchange.getRequestMethod();
            if (requestContentType != null
                && requestContentType.startsWith("multipart/form-data")
                && targetPath.endsWith("/chunk")) {
                MultipartFormData upload = MultipartFormData.parse(new ByteArrayInputStream(requestBody), requestContentType);
                if (upload == null || upload.fileName() == null || upload.bytes().length == 0) {
                    HttpUtils.sendJson(exchange, 400, "{\"error\":\"Live upload payload is missing its media chunk.\"}");
                    return;
                }
                Path proxyUploadDir = projectRoot.resolve("output").resolve("live-proxy-uploads");
                Files.createDirectories(proxyUploadDir);
                String safeFileName = upload.fileName().replaceAll("[^a-zA-Z0-9._-]", "_");
                Path proxyUploadPath = proxyUploadDir.resolve(Instant.now().toEpochMilli() + "-" + safeFileName);
                Files.write(proxyUploadPath, upload.bytes());
                requestBody = new byte[0];
                requestContentType = null;
                targetMethod = "GET";
                targetUrl = aiServiceUrl + targetPath + "-path" + buildChunkPathQuery(proxyUploadPath, upload.fields(), query);
            }
            HttpResponse<byte[]> response;
            try {
                response = sendHttpRequest(
                    targetUrl,
                    targetMethod,
                    requestBody,
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    requestContentType
                );
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Live request was interrupted.", exception);
            }

            String responseContentType = response.headers().firstValue("Content-Type").orElse("application/json; charset=utf-8");
            HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), responseContentType);
        }
    }

    private static final class GitLabProxyHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            HttpUtils.requireMethod(exchange, "POST");
            String aiServiceUrl = aiServiceUrl();
            if (aiServiceUrl == null) {
                HttpUtils.sendJson(exchange, 503, "{\"error\":\"GitLab backend is unavailable.\"}");
                return;
            }

            String requestPath = exchange.getRequestURI().getPath();
            String suffix = requestPath.substring("/api/gitlab".length());
            String targetPath = switch (suffix) {
                case "/plan" -> "/api/v1/gitlab/plan";
                case "/sync" -> "/api/v1/gitlab/sync";
                default -> null;
            };
            if (targetPath == null) {
                HttpUtils.sendJson(exchange, 404, "{\"error\":\"GitLab route not found.\"}");
                return;
            }

            String query = exchange.getRequestURI().getRawQuery();
            String targetUrl = aiServiceUrl + targetPath + (query == null || query.isBlank() ? "" : "?" + query);
            HttpResponse<byte[]> response;
            try {
                response = sendHttpRequest(
                    targetUrl,
                    "POST",
                    exchange.getRequestBody().readAllBytes(),
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    "application/json"
                );
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("GitLab request was interrupted.", exception);
            }

            String responseContentType = response.headers().firstValue("Content-Type").orElse("application/json; charset=utf-8");
            HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), responseContentType);
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
            value = "http://127.0.0.1:8000";
        }
        return value.replaceAll("/+$", "");
    }

    private static void proxyJson(HttpExchange exchange, String targetUrl) throws IOException {
        HttpResponse<byte[]> response;
        try {
            response = sendHttpRequest(
                targetUrl,
                exchange.getRequestMethod(),
                exchange.getRequestBody().readAllBytes(),
                exchange.getRequestHeaders().getFirst("Authorization"),
                "application/json"
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
            response = sendHttpRequest(
                targetUrl,
                exchange.getRequestMethod(),
                new byte[0],
                exchange.getRequestHeaders().getFirst("Authorization"),
                null
            );
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("Report request to AI service was interrupted.", exception);
        }
        HttpUtils.sendBytes(exchange, response.statusCode(), response.body(), HttpUtils.contentType(fileName));
    }

    private static HttpResponse<byte[]> sendHttpRequest(
        String targetUrl,
        String method,
        byte[] body,
        String authorizationHeader,
        String contentType
    ) throws IOException, InterruptedException {
        HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
            .uri(URI.create(targetUrl))
            .timeout(Duration.ofMinutes(5));

        if (authorizationHeader != null && !authorizationHeader.isBlank()) {
            requestBuilder.header("Authorization", authorizationHeader);
        }
        if (!"GET".equalsIgnoreCase(method) && contentType != null && !contentType.isBlank()) {
            requestBuilder.header("Content-Type", contentType);
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

    private static String buildChunkPathQuery(Path proxyUploadPath, Map<String, String> fields, String existingQuery) {
        StringBuilder query = new StringBuilder();
        if (existingQuery != null && !existingQuery.isBlank()) {
            query.append("?").append(existingQuery);
        } else {
            query.append("?");
        }
        appendQueryParam(query, "shared_file_path", proxyUploadPath.toString());
        for (Map.Entry<String, String> field : fields.entrySet()) {
            appendQueryParam(query, field.getKey(), field.getValue());
        }
        return query.toString();
    }

    private static void appendQueryParam(StringBuilder query, String key, String value) {
        if (query.length() > 1 && query.charAt(query.length() - 1) != '?' && query.charAt(query.length() - 1) != '&') {
            query.append("&");
        }
        query.append(URLEncoder.encode(key, StandardCharsets.UTF_8))
            .append("=")
            .append(URLEncoder.encode(value, StandardCharsets.UTF_8));
    }
}
