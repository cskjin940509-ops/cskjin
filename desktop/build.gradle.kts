import java.util.Properties
import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    id("org.jetbrains.kotlin.jvm")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.compose")
}

val release = Properties().apply { rootProject.file("version.properties").inputStream().use { load(it) } }
kotlin {
    jvmToolchain(17)
    sourceSets.main {
        // Compile the actual Android screen sources, never a separate desktop copy.
        kotlin.srcDir("../app/src/main/java/com/rui/astockstrategy/v6")
        kotlin.srcDir(rootProject.layout.buildDirectory.dir("generated/version"))
    }
}
tasks.named("compileKotlin") { dependsOn(rootProject.tasks.named("generateAppVersion")) }
dependencies {
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation("org.jetbrains.compose.material:material-icons-extended:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.10.2")
    implementation("org.json:json:20250517")
}
compose.desktop {
    application {
        mainClass = "com.rui.astockstrategy.desktop.MainKt"
        nativeDistributions {
            targetFormats(TargetFormat.Exe)
            packageName = "AStockSelection"
            packageVersion = release.getProperty("versionName")
            description = "A股筛选池 — 市场、机会、组合与研究"
            vendor = "AStock Research"
            includeAllModules = true
            windows {
                shortcut = true
                menu = true
                menuGroup = "AStockSelection"
                dirChooser = true
                perUserInstall = true
                upgradeUuid = "b7a4b515-d0d8-4e79-a568-1f61ec442a76"
            }
        }
    }
}
