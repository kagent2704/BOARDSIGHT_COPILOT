package com.boardsight.service;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

public final class PythonPipelineRunner {
    private final Path projectRoot;
    private final String pythonCommand;

    public PythonPipelineRunner(Path projectRoot, String pythonCommand) {
        this.projectRoot = projectRoot;
        this.pythonCommand = pythonCommand;
    }

    public PipelineRunResult run(Path videoPath, Path outputDirectory, String authorizationHeader) throws IOException, InterruptedException {
        return run(videoPath, outputDirectory, authorizationHeader, null, null, null);
    }

    public PipelineRunResult run(
        Path videoPath,
        Path outputDirectory,
        String authorizationHeader,
        Double startSeconds,
        Double endSeconds,
        String analysisProfile
    ) throws IOException, InterruptedException {
        if (!Files.exists(videoPath)) {
            throw new IOException("Video file does not exist: " + videoPath);
        }

        Files.createDirectories(outputDirectory);
        String aiServiceUrl = System.getenv("BOARDSIGHT_AI_URL");
        if (aiServiceUrl != null && !aiServiceUrl.isBlank()) {
            return runRemote(videoPath, outputDirectory, aiServiceUrl, authorizationHeader, startSeconds, endSeconds, analysisProfile);
        }
        return runLocal(videoPath, outputDirectory, startSeconds, endSeconds, analysisProfile);
    }

    public PipelineRunResult run(Path videoPath, Path outputDirectory) throws IOException, InterruptedException {
        return run(videoPath, outputDirectory, null, null, null, null);
    }

    private PipelineRunResult runLocal(
        Path videoPath,
        Path outputDirectory,
        Double startSeconds,
        Double endSeconds,
        String analysisProfile
    ) throws IOException, InterruptedException {
        Path cliPath = projectRoot.resolve("python-ai").resolve("boardsight_ai").resolve("cli.py");
        Path resultPath = outputDirectory.resolve("boardsight_result.json");

        List<String> command = new ArrayList<>();
        command.add(pythonCommand);
        command.add(cliPath.toString());
        command.add("--video");
        command.add(videoPath.toString());
        command.add("--output-dir");
        command.add(outputDirectory.toString());
        command.add("--result-file");
        command.add(resultPath.toString());
        if (startSeconds != null) {
            command.add("--start-seconds");
            command.add(Double.toString(startSeconds));
        }
        if (endSeconds != null) {
            command.add("--end-seconds");
            command.add(Double.toString(endSeconds));
        }
        if (analysisProfile != null && !analysisProfile.isBlank()) {
            command.add("--analysis-profile");
            command.add(analysisProfile);
        }

        ProcessBuilder builder = new ProcessBuilder(command);
        builder.directory(projectRoot.toFile());
        builder.redirectErrorStream(true);
        Process process = builder.start();

        try (BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("[python] " + line);
            }
        }

        int exitCode = process.waitFor();
        if (exitCode != 0) {
            throw new IOException("Python pipeline failed with exit code " + exitCode);
        }

        return new PipelineRunResult(exitCode, outputDirectory, resultPath);
    }

    private PipelineRunResult runRemote(
        Path videoPath,
        Path outputDirectory,
        String aiServiceUrl,
        String authorizationHeader,
        Double startSeconds,
        Double endSeconds,
        String analysisProfile
    ) throws IOException, InterruptedException {
        Path resultPath = outputDirectory.resolve("boardsight_result.json");
        String encodedOutputDir = URLEncoder.encode(outputDirectory.getFileName().toString(), StandardCharsets.UTF_8);
        String encodedFilePath = URLEncoder.encode(videoPath.toString(), StandardCharsets.UTF_8);
        StringBuilder requestBody = new StringBuilder();
        requestBody.append("{\"file_path\":\"").append(escapeJson(videoPath.toString())).append("\",\"output_dir_name\":\"")
            .append(escapeJson(outputDirectory.getFileName().toString())).append("\"");
        StringBuilder querySuffix = new StringBuilder();
        if (startSeconds != null) {
            requestBody.append(",\"start_seconds\":").append(startSeconds);
            querySuffix.append("&start_seconds=").append(URLEncoder.encode(Double.toString(startSeconds), StandardCharsets.UTF_8));
        }
        if (endSeconds != null) {
            requestBody.append(",\"end_seconds\":").append(endSeconds);
            querySuffix.append("&end_seconds=").append(URLEncoder.encode(Double.toString(endSeconds), StandardCharsets.UTF_8));
        }
        if (analysisProfile != null && !analysisProfile.isBlank()) {
            requestBody.append(",\"analysis_profile\":\"").append(escapeJson(analysisProfile)).append("\"");
            querySuffix.append("&analysis_profile=").append(URLEncoder.encode(analysisProfile, StandardCharsets.UTF_8));
        }
        requestBody.append("}");

        HttpRequest.Builder requestBuilder = HttpRequest.newBuilder()
            .uri(URI.create(
                aiServiceUrl.replaceAll("/+$", "")
                    + "/api/v1/pipeline/run-path?output_dir_name="
                    + encodedOutputDir
                    + "&file_path="
                    + encodedFilePath
                    + querySuffix
            ))
            .timeout(Duration.ofMinutes(30))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody.toString(), StandardCharsets.UTF_8));

        if (authorizationHeader != null && !authorizationHeader.isBlank()) {
            requestBuilder.header("Authorization", authorizationHeader);
        }

        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();

        HttpResponse<String> response = client.send(requestBuilder.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IOException("Python AI service failed with HTTP " + response.statusCode() + ": " + response.body());
        }

        if (!Files.exists(resultPath)) {
            Files.writeString(resultPath, response.body(), StandardCharsets.UTF_8);
        }
        return new PipelineRunResult(0, outputDirectory, resultPath);
    }

    private static String escapeJson(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
