import java.util.Properties
plugins {
    id("com.android.application") version "8.13.2" apply false
    id("org.jetbrains.kotlin.jvm") version "2.3.0" apply false
    id("org.jetbrains.compose") version "1.10.0" apply false
    id("org.jetbrains.kotlin.android") version "2.3.0" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.3.0" apply false
}

val releaseProperties = Properties().apply { rootProject.file("version.properties").inputStream().use { load(it) } }
val appVersionName = releaseProperties.getProperty("versionName")
val generateAppVersion by tasks.registering {
    inputs.file("version.properties")
    val output = layout.buildDirectory.file("generated/version/com/rui/astockstrategy/v6/AppVersion.kt")
    outputs.file(output)
    doLast {
        output.get().asFile.apply {
            parentFile.mkdirs()
            writeText("package com.rui.astockstrategy.v6\nobject AppVersion { const val name = \"$appVersionName\" }\n")
        }
    }
}
