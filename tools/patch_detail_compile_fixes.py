from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/DetailScreens.kt')
s = p.read_text(encoding='utf-8')

# Mutable nullable JSON vars are not smart-cast by Kotlin; freeze them into local vals.
s = s.replace(
'''        day ?: return@withContext null\n\n        var selected: JSONObject? = null\n        val selectedArr = day.optJSONArray("selectedSectors")''',
'''        val dayObj = day ?: return@withContext null\n\n        var selected: JSONObject? = null\n        val selectedArr = dayObj.optJSONArray("selectedSectors")'''
)
s = s.replace('''        val hm = day.optJSONObject("boardHeatmap")''', '''        val hm = dayObj.optJSONObject("boardHeatmap")''')

s = s.replace(
'''        val x = day?.optJSONObject("stocks")?.optJSONObject(code) ?: return@withContext null\n        val ps = mutableListOf<String>()''',
'''        val dayObj = day ?: return@withContext null\n        val x = dayObj.optJSONObject("stocks")?.optJSONObject(code) ?: return@withContext null\n        val ps = mutableListOf<String>()'''
)
s = s.replace('''            val po = day.optJSONObject("pools")''', '''            val po = dayObj.optJSONObject("pools")''')

s = s.replace('''            up = h?.optInt("up")?.takeIf { h.has("up") },\n            down = h?.optInt("down")?.takeIf { h.has("down") },\n            flat = h?.optInt("flat")?.takeIf { h.has("flat") },''',
'''            up = if (h?.has("up") == true) h.optInt("up") else null,\n            down = if (h?.has("down") == true) h.optInt("down") else null,\n            flat = if (h?.has("flat") == true) h.optInt("flat") else null,''')

p.write_text(s, encoding='utf-8')
