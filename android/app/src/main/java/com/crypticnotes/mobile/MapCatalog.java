package com.crypticnotes.mobile;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Read-only view of the bundled map library.
 *
 * Reads `assets/maps/floors.json` — the same manifest the desktop client treats
 * as the source of truth — straight out of the APK, so the list is available
 * without starting screen capture. Nothing here writes to the library.
 */
final class MapCatalog {
    private MapCatalog() {}

    static final class Entry {
        final String mapId, name, difficulty, mode, source, review;
        final List<Integer> floors = new ArrayList<>();
        int width, height;

        Entry(String mapId, String name, String difficulty, String mode, String source, String review) {
            this.mapId = mapId;
            this.name = name;
            this.difficulty = difficulty;
            this.mode = mode;
            this.source = source;
            this.review = review;
        }
    }

    private static List<Entry> cached;

    /** The manifest is fixed for the installed APK, so it is parsed once. */
    static synchronized List<Entry> load(Context context) {
        if (cached == null) cached = read(context);
        return cached;
    }

    private static List<Entry> read(Context context) {
        List<Entry> entries = new ArrayList<>();
        try (InputStream in = context.getAssets().open("maps/floors.json")) {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] block = new byte[65536];
            int read;
            while ((read = in.read(block)) != -1) buffer.write(block, 0, read);
            JSONArray references = new JSONObject(buffer.toString("UTF-8")).optJSONArray("references");
            if (references == null) return entries;
            for (int i = 0; i < references.length(); i++) {
                JSONObject item = references.optJSONObject(i);
                if (item == null) continue;
                String mapId = item.optString("map_id");
                if (mapId.isEmpty()) continue;
                Entry entry = new Entry(mapId,
                        item.optString("name", mapId.substring(mapId.lastIndexOf('/') + 1)),
                        item.optString("difficulty"), item.optString("mode", null),
                        item.optString("source"), item.optString("review"));
                JSONArray size = item.optJSONArray("size");
                if (size != null && size.length() >= 2) {
                    entry.width = size.optInt(0);
                    entry.height = size.optInt(1);
                }
                JSONArray regions = item.optJSONArray("regions");
                if (regions != null) {
                    for (int r = 0; r < regions.length(); r++) {
                        JSONObject region = regions.optJSONObject(r);
                        if (region != null && region.has("floor")) entry.floors.add(region.optInt("floor"));
                    }
                }
                entries.add(entry);
            }
        } catch (Exception ignored) {
            // A missing or malformed manifest leaves the screen empty rather than crashing.
        }
        return entries;
    }

    /** 1F/2F first, basement last — same order as the desktop list. */
    static String floorText(List<Integer> floors) {
        List<Integer> sorted = new ArrayList<>(floors);
        Collections.sort(sorted, (a, b) -> {
            int left = a == -1 ? 1 : 0, right = b == -1 ? 1 : 0;
            return left != right ? left - right : a - b;
        });
        StringBuilder text = new StringBuilder();
        for (int floor : sorted) {
            if (text.length() > 0) text.append('·');
            text.append(floor == 1 ? "1F" : floor == 2 ? "2F" : floor == -1 ? "地下室" : floor + "F");
        }
        return text.toString();
    }

    static String contextText(String difficulty, String mode) {
        if ("hard".equals(difficulty)) return "困难";
        String suffix = "solo".equals(mode) ? "单人" : "duo".equals(mode) ? "多人" : "";
        return "噩梦·" + suffix;
    }
}
