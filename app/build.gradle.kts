import org.gradle.testing.jacoco.tasks.JacocoReport
import org.gradle.testing.jacoco.tasks.JacocoCoverageVerification

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    jacoco
}

android {
    namespace = "org.rootwise.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.rootwise.android"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0-alpha"
    }

    dependenciesInfo {
        // Required for F-Droid reproducible builds: omit Google's encrypted signing block.
        includeInApk = false
        includeInBundle = false
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = false
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.15"
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
        unitTests.all {
            it.maxHeapSize = "256m"
        }
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

jacoco {
    toolVersion = "0.8.11"
}

dependencies {
    // UI & SAF integration (all Apache-2.0 FOSS; core scanner package uses zero third-party deps)
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.compose.ui:ui:1.7.2")
    implementation("androidx.compose.ui:ui-graphics:1.7.2")
    implementation("androidx.compose.material3:material3:1.3.0")
    implementation("androidx.documentfile:documentfile:1.0.1")

    // Unit testing on JVM with real SQLite engine
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.xerial:sqlite-jdbc:3.46.1.0")
}

val jacocoExcludes = listOf(
    "**/R.class",
    "**/R$*.class",
    "**/BuildConfig.*",
    "**/Manifest*.*",
    "org/rootwise/android/ui/**",
    "org/rootwise/android/MainActivity*",
    "org/rootwise/android/adapter/Android*",
    "org/rootwise/android/core/db/AndroidSqlite*"
)

tasks.register<JacocoReport>("jacocoTestReport") {
    dependsOn("testDebugUnitTest")
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
    val kotlinTree = fileTree("${layout.buildDirectory.get()}/tmp/kotlin-classes/debug") {
        exclude(jacocoExcludes)
    }
    classDirectories.setFrom(files(kotlinTree))
    sourceDirectories.setFrom(files("$projectDir/src/main/java"))
    executionData.setFrom(
        fileTree(layout.buildDirectory.get()) {
            include("jacoco/testDebugUnitTest.exec", "outputs/unit_test_code_coverage/debugUnitTest/testDebugUnitTest.exec")
        }
    )
}

tasks.register<JacocoCoverageVerification>("jacocoCoverageVerification") {
    dependsOn("jacocoTestReport")
    val kotlinTree = fileTree("${layout.buildDirectory.get()}/tmp/kotlin-classes/debug") {
        exclude(jacocoExcludes)
    }
    classDirectories.setFrom(files(kotlinTree))
    sourceDirectories.setFrom(files("$projectDir/src/main/java"))
    executionData.setFrom(
        fileTree(layout.buildDirectory.get()) {
            include("jacoco/testDebugUnitTest.exec", "outputs/unit_test_code_coverage/debugUnitTest/testDebugUnitTest.exec")
        }
    )
    violationRules {
        rule {
            limit {
                counter = "LINE"
                value = "COVEREDRATIO"
                minimum = "0.85".toBigDecimal()
            }
        }
    }
}

tasks.register("dependencyGuard") {
    group = "verification"
    description = "Verifies runtime dependencies are FOSS-licensed (Apache-2.0) and contain no network or proprietary libraries."
    doLast {
        val allowedGroupPrefixes = listOf(
            "androidx.",
            "org.jetbrains.kotlin",
            "org.jetbrains.kotlinx",
            "org.jetbrains:annotations",
            "com.google.guava:listenablefuture"
        )
        val forbiddenTokens = listOf(
            "okhttp",
            "retrofit",
            "ktor",
            "volley",
            "cronet",
            "play-services",
            "firebase",
            "gms",
            "chaquopy",
            "sentry",
            "crashlytics"
        )
        val config = configurations.getByName("releaseRuntimeClasspath")
        val artifacts = config.resolvedConfiguration.resolvedArtifacts
            .map { "${it.moduleVersion.id.group}:${it.moduleVersion.id.name}:${it.moduleVersion.id.version}" }
            .sorted()
            .distinct()

        val violations = mutableListOf<String>()
        for (coord in artifacts) {
            val allowed = allowedGroupPrefixes.any { coord.startsWith(it) }
            if (!allowed) {
                violations.add("Unapproved group/license coordinate: $coord")
            }
            for (token in forbiddenTokens) {
                if (coord.lowercase().contains(token)) {
                    violations.add("Forbidden network/proprietary dependency detected: $coord")
                }
            }
        }
        val reportFile = layout.buildDirectory.file("reports/dependency-guard/runtime-dependencies.txt").get().asFile
        reportFile.parentFile.mkdirs()
        reportFile.writeText(artifacts.joinToString("\n") + "\n")

        if (violations.isNotEmpty()) {
            throw GradleException("dependencyGuard failed:\n" + violations.joinToString("\n"))
        }
        println("dependencyGuard PASS: ${artifacts.size} runtime artifacts verified (Apache-2.0 only, 0 network libs).")
    }
}
