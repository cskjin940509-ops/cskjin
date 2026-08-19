from pathlib import Path

# 1) DataApi: allow choosing Eastmoney realtime or delayed host.
p = Path('app/src/main/java/com/rui/astockstrategy/v6/V6Activity.kt')
s = p.read_text(encoding='utf-8')

old = '''    suspend fun fetchBoards(type: String): List<Board> = withContext(Dispatchers.IO) {\n        val fs = if (type == "industry") "m:90+t:2+f:!50" else "m:90+t:3+f:!50"\n        boardList(fs, type)\n    }\n\n    private fun boardList(fs0: String, type: String): List<Board> {\n        val fs = URLEncoder.encode(fs0, "UTF-8")\n        val url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106"'''
new = '''    suspend fun fetchBoards(type: String, delayed: Boolean = false): List<Board> = withContext(Dispatchers.IO) {\n        val fs = if (type == "industry") "m:90+t:2+f:!50" else "m:90+t:3+f:!50"\n        boardList(fs, type, delayed)\n    }\n\n    private fun boardList(fs0: String, type: String, delayed: Boolean = false): List<Board> {\n        val fs = URLEncoder.encode(fs0, "UTF-8")\n        val host = if (delayed) "push2delay.eastmoney.com" else "push2.eastmoney.com"\n        val url = "https://$host/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=$fs&fields=f3,f6,f12,f14,f62,f184,f104,f105,f106"'''
if old not in s:
    raise SystemExit('DataApi board source block not found')
s = s.replace(old, new, 1)

# A successful fetch timestamp is not enough to claim realtime when the fallback payload is stale.
s = s.replace(
    'LiveBadge("板块", freshnessLabel(now, boardOkAt, 70000, "实时", "已过期"), now - boardOkAt <= 70000, Modifier.weight(1f))',
    'LiveBadge("板块", if (ResilientDataApi.boardIsCurrent) freshnessLabel(now, boardOkAt, 70000, "实时", "已过期") else ResilientDataApi.boardSource, ResilientDataApi.boardIsCurrent && now - boardOkAt <= 70000, Modifier.weight(1f))'
)
s = s.replace(
    'LiveBadge("主线预览", freshnessLabel(now, boardOkAt, 70000, "实时", "已过期"), now - boardOkAt <= 70000, Modifier.fillMaxWidth())',
    'LiveBadge("主线预览", if (ResilientDataApi.boardIsCurrent) freshnessLabel(now, boardOkAt, 70000, "实时", "已过期") else ResilientDataApi.boardSource, ResilientDataApi.boardIsCurrent && now - boardOkAt <= 70000, Modifier.fillMaxWidth())'
)
p.write_text(s, encoding='utf-8')

# 2) ResilientDataApi: realtime -> delayed -> GitHub snapshot, with explicit provenance/freshness.
g = Path('app/src/main/java/com/rui/astockstrategy/v6/GatewayFallback.kt')
gs = g.read_text(encoding='utf-8')
if 'import java.time.LocalDate' not in gs:
    gs = gs.replace('import java.net.URL\n', 'import java.net.URL\nimport java.time.LocalDate\nimport java.time.ZoneId\n')

gs = gs.replace(
'''    @Volatile var boardSource: String = "东方财富"\n        private set\n    @Volatile var gatewayGeneratedAt: String? = null''',
'''    @Volatile var boardSource: String = "东方财富实时"\n        private set\n    @Volatile var boardIsCurrent: Boolean = false\n        private set\n    @Volatile var gatewayGeneratedAt: String? = null'''
)

old_pair = '''    suspend fun fetchBoardsPair(): Pair<List<Board>, List<Board>> {\n        val directIndustry = runCatching { DataApi.fetchBoards("industry") }.getOrNull().orEmpty()\n        val directConcept = runCatching { DataApi.fetchBoards("concept") }.getOrNull().orEmpty()\n        if (directIndustry.isNotEmpty() || directConcept.isNotEmpty()) {\n            boardSource = "东方财富"\n            return directIndustry to directConcept\n        }\n        val root = runCatching { gatewayRoot() }.getOrNull()\n        if (root == null) {\n            boardSource = "板块源不可用"\n            return emptyList<Board>() to emptyList()\n        }\n        val heat = root.optJSONObject("boardHeatmap")\n        val industry = parseBoards(heat?.optJSONArray("industry"), "industry")\n        val concept = parseBoards(heat?.optJSONArray("concept"), "concept")\n        boardSource = if (industry.isNotEmpty() || concept.isNotEmpty()) "备用市场快照" else "板块源不可用"\n        gatewayGeneratedAt = root.optString("generatedAt").takeIf { it.isNotBlank() }\n        return industry to concept\n    }'''
new_pair = '''    suspend fun fetchBoardsPair(): Pair<List<Board>, List<Board>> {\n        // Tier 1: Eastmoney realtime.\n        val directIndustry = runCatching { DataApi.fetchBoards("industry", delayed = false) }.getOrNull().orEmpty()\n        val directConcept = runCatching { DataApi.fetchBoards("concept", delayed = false) }.getOrNull().orEmpty()\n        if (directIndustry.isNotEmpty() || directConcept.isNotEmpty()) {\n            boardSource = "东方财富实时"\n            boardIsCurrent = true\n            return directIndustry to directConcept\n        }\n\n        // Tier 2: Eastmoney delayed host. It is current-session data but may lag roughly 15 minutes.\n        val delayedIndustry = runCatching { DataApi.fetchBoards("industry", delayed = true) }.getOrNull().orEmpty()\n        val delayedConcept = runCatching { DataApi.fetchBoards("concept", delayed = true) }.getOrNull().orEmpty()\n        if (delayedIndustry.isNotEmpty() || delayedConcept.isNotEmpty()) {\n            boardSource = "东方财富延迟源（约15分钟）"\n            boardIsCurrent = true\n            return delayedIndustry to delayedConcept\n        }\n\n        // Tier 3: frozen GitHub gateway. Never label an old snapshot as realtime.\n        val root = runCatching { gatewayRoot() }.getOrNull()\n        if (root == null) {\n            boardSource = "板块源不可用"\n            boardIsCurrent = false\n            return emptyList<Board>() to emptyList()\n        }\n        val heat = root.optJSONObject("boardHeatmap")\n        val industry = parseBoards(heat?.optJSONArray("industry"), "industry")\n        val concept = parseBoards(heat?.optJSONArray("concept"), "concept")\n        gatewayGeneratedAt = root.optString("generatedAt").takeIf { it.isNotBlank() }\n        val sourceDate = root.optJSONObject("marketSnapshot")?.optString("sourceDate")?.takeIf { it.isNotBlank() }\n        val today = LocalDate.now(ZoneId.of("Asia/Shanghai")).toString()\n        boardIsCurrent = sourceDate == today\n        val time = gatewayGeneratedAt?.let { v -> if (v.length >= 16) v.substring(11, 16) else null }\n        boardSource = if (industry.isNotEmpty() || concept.isNotEmpty()) {\n            "备用快照 ${sourceDate ?: "日期未知"}${time?.let { " $it" } ?: ""}"\n        } else {\n            "板块源不可用"\n        }\n        return industry to concept\n    }'''
if old_pair not in gs:
    raise SystemExit('ResilientDataApi board pair block not found')
gs = gs.replace(old_pair, new_pair, 1)
g.write_text(gs, encoding='utf-8')

# 3) Version v1.5 after v1.4 data-audit patch.
b = Path('app/build.gradle.kts')
bs = b.read_text(encoding='utf-8')
bs = bs.replace('versionCode = 15', 'versionCode = 16')
bs = bs.replace('versionName = "1.4.0"', 'versionName = "1.5.0"')
b.write_text(bs, encoding='utf-8')
