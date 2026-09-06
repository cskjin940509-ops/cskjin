package com.rui.astockstrategy.desktop

import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberWindowState
import com.rui.astockstrategy.v6.*
import java.nio.file.Files
import java.nio.file.Path
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import java.awt.Desktop
import java.net.URI

fun main(args: Array<String>) {
    if ("--self-test" in args) { storageSelfTest(); return }
    val root = System.getProperty("astock.dataDir")?.let { Path.of(it) } ?:
        Path.of(System.getenv("LOCALAPPDATA") ?: System.getProperty("user.home"), "AStockResearch", "Data")
    Files.createDirectories(root)
    val channel = FileChannel.open(root.resolve("application.lock"), StandardOpenOption.CREATE, StandardOpenOption.WRITE)
    val lock = channel.tryLock()
    if (lock == null) {
        javax.swing.JOptionPane.showMessageDialog(null, "A股筛选池已在运行，请切换到已打开的窗口。")
        channel.close()
        return
    }
    val context = AppContext(root)
    BackendClient.initialize(context)
    try {
        application {
            Window(onCloseRequest = ::exitApplication, title = "A股筛选池 ${AppVersion.name}",
                state = rememberWindowState(width = 1120.dp, height = 840.dp)) {
                window.minimumSize = java.awt.Dimension(760, 640)
                CompositionLocalProvider(LocalAppContext provides context) { AStockV6() }
                if ("--smoke-test" in args) {
                    androidx.compose.runtime.LaunchedEffect(Unit) {
                        kotlinx.coroutines.delay(12000)
                        val output = Path.of(System.getenv("ASTOCK_SMOKE_OUTPUT") ?: "desktop-smoke.png")
                        val location = window.locationOnScreen
                        val shot = java.awt.Robot().createScreenCapture(java.awt.Rectangle(location.x, location.y, window.width, window.height))
                        javax.imageio.ImageIO.write(shot, "png", output.toFile())
                        exitApplication()
                    }
                }
            }
        }
    } finally { lock.release(); channel.close() }
}

private fun storageSelfTest() {
    val directory = Files.createTempDirectory("astock-desktop-test-")
    try {
        val context = AppContext(directory)
        val preferences = context.getSharedPreferences("test", AppContext.MODE_PRIVATE)
        val largeBackup = "研究账本".repeat(12000)
        preferences.edit().putString("backup", largeBackup).putFloat("price", 12.5f).apply()
        val reopened = AppContext(directory).getSharedPreferences("test", 0)
        check(reopened.getString("backup", null) == largeBackup)
        check(reopened.getFloat("price", 0f) == 12.5f)
        reopened.edit().remove("price").apply()
        check(reopened.getFloat("price", -1f) == -1f)
        val cache = BackendCache(context)
        cache.put("astock_ai_portfolio/latest.json", "{\"ok\":true}", 1234, "test", null)
        val saved = BackendCache(AppContext(directory)).get("astock_ai_portfolio/latest.json")
        check(saved?.body == "{\"ok\":true}" && saved.fetchedAt == 1234L)
        check(cache.get("missing") == null)
        check(TradeLedger.records(context).isEmpty())
        check(TradeLedger.importMerge(context, TradeLedger.exportJson(context)) == 0)
        Files.writeString(Path.of(System.getenv("ASTOCK_SELF_TEST_OUTPUT") ?: "desktop-self-test.txt"),
            "PASS ${AppVersion.name}: preferences restart/large journal/removal, cache restart, journal backup compatibility")
    } finally { directory.toFile().deleteRecursively() }
}
