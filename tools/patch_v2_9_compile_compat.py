from pathlib import Path

p = Path('app/src/main/java/com/rui/astockstrategy/v6/V29HistoryPatternLab.kt')
s = p.read_text(encoding='utf-8')

repls = {
    '''        val full=t?.optJSONObject("full"); val r60=t?.optJSONObject("recent60"); val r20=t?.optJSONObject("recent20"); val j=t?.optJSONObject("judgement")''': '''        val full=t?.optJSONObject("full")
        val r60=t?.optJSONObject("recent60")
        val r20=t?.optJSONObject("recent20")
        val j=t?.optJSONObject("judgement")''',
    '''        val lo=min(-0.01, vals.minOrNull() ?: -0.01); val hi=max(0.01, vals.maxOrNull() ?: 0.01); val range=hi-lo''': '''        val lo=min(-0.01, vals.minOrNull() ?: -0.01)
        val hi=max(0.01, vals.maxOrNull() ?: 0.01)
        val range=hi-lo''',
    '''                val p=Path(); var first=true''': '''                val p=Path()
                var first=true''',
    '''        val xmin=min(-0.01,points.minOf{it.mae}); val xmax=max(0.01,points.maxOf{it.mae}); val ymin=min(-0.01,points.minOf{it.mfe}); val ymax=max(0.01,points.maxOf{it.mfe})''': '''        val xmin=min(-0.01,points.minOf{it.mae})
        val xmax=max(0.01,points.maxOf{it.mae})
        val ymin=min(-0.01,points.minOf{it.mfe})
        val ymax=max(0.01,points.maxOf{it.mfe})''',
    '''            fun x(v:Double)=((v-xmin)/(xmax-xmin)*size.width).toFloat(); fun y(v:Double)=((ymax-v)/(ymax-ymin)*size.height).toFloat()''': '''            fun x(v:Double)=((v-xmin)/(xmax-xmin)*size.width).toFloat()
            fun y(v:Double)=((ymax-v)/(ymax-ymin)*size.height).toFloat()''',
    '''        Text(o.optString("definitionZh"), color = HMuted29, fontSize = 8.sp)''': '''        Text(o?.optString("definitionZh") ?: "", color = HMuted29, fontSize = 8.sp)''',
}

for old, new in repls.items():
    s = s.replace(old, new)

# Guard against accidental remaining same-line local declaration patterns that are
# hard for the Kotlin parser in this generated Compose file.
s = s.replace('; val ', '\n        val ')
s = s.replace('; var ', '\n        var ')
s = s.replace('; fun ', '\n            fun ')

p.write_text(s, encoding='utf-8')
print('v2.9 history compile compatibility applied')
