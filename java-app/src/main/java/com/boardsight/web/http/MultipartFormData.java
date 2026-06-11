package com.boardsight.web.http;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public record MultipartFormData(String fileName, byte[] bytes, Map<String, String> fields) {
    public static MultipartFormData parse(InputStream input, String contentType) throws IOException {
        if (contentType == null || !contentType.contains("boundary=")) {
            return null;
        }

        String boundaryToken = contentType.substring(contentType.indexOf("boundary=") + 9).trim();
        if (boundaryToken.startsWith("\"") && boundaryToken.endsWith("\"") && boundaryToken.length() >= 2) {
            boundaryToken = boundaryToken.substring(1, boundaryToken.length() - 1);
        }

        String boundary = "--" + boundaryToken;
        byte[] body = readAllBytes(input);
        String text = new String(body, StandardCharsets.ISO_8859_1);
        String[] parts = text.split(boundary);

        String fileName = null;
        byte[] fileBytes = new byte[0];
        Map<String, String> fields = new LinkedHashMap<>();

        for (String rawPart : parts) {
            String part = rawPart.stripLeading();
            if (part.isBlank() || "--".equals(part.trim())) {
                continue;
            }

            int headerEnd = part.indexOf("\r\n\r\n");
            if (headerEnd < 0) {
                continue;
            }

            String headers = part.substring(0, headerEnd);
            String fieldName = extractDispositionValue(headers, "name");
            if (fieldName == null || fieldName.isBlank()) {
                continue;
            }

            int dataStart = headerEnd + 4;
            int dataEnd = part.lastIndexOf("\r\n");
            if (dataEnd < dataStart) {
                dataEnd = part.length();
            }
            byte[] partBytes = part.substring(dataStart, dataEnd).getBytes(StandardCharsets.ISO_8859_1);
            String candidateFileName = extractDispositionValue(headers, "filename");

            if (candidateFileName != null && !candidateFileName.isBlank()) {
                fileName = candidateFileName;
                fileBytes = partBytes;
            } else {
                fields.put(fieldName, new String(partBytes, StandardCharsets.UTF_8).trim());
            }
        }

        if (fileName == null) {
            return null;
        }
        return new MultipartFormData(fileName, fileBytes, fields);
    }

    private static String extractDispositionValue(String headers, String key) {
        String token = key + "=\"";
        int start = headers.indexOf(token);
        if (start < 0) {
            return null;
        }
        start += token.length();
        int end = headers.indexOf("\"", start);
        if (end < 0) {
            return null;
        }
        return headers.substring(start, end);
    }

    private static byte[] readAllBytes(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        input.transferTo(output);
        return output.toByteArray();
    }
}
