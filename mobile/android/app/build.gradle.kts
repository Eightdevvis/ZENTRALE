import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Release signing (memory/system/zen_mobile.md "Self-update"). The key never
// lives in the repo: key.properties (storeFile, storePassword, keyAlias,
// keyPassword) is read from $ZENTRALE_ANDROID_KEY_PROPERTIES or
// ~/.config/zentrale/android/key.properties. A relative storeFile is taken
// relative to that file. Missing → debug signing with a loud warning; such an
// APK must never be published (scripts/publish_phone_app.py refuses it).
val releaseKeyFile: File = File(
    System.getenv("ZENTRALE_ANDROID_KEY_PROPERTIES")
        ?: "${System.getProperty("user.home")}/.config/zentrale/android/key.properties"
)
val releaseKey: Properties? = if (releaseKeyFile.isFile) {
    Properties().apply { releaseKeyFile.inputStream().use { load(it) } }
} else {
    null
}

// Distribution: "direct" (our own APK, updates itself from the ZENTRALE cloud)
// or "play" (Google Play updates it; self-update is off). Gradle property
// -Pzentrale.distribution=play or env ZENTRALE_DISTRIBUTION=play.
val distribution: String = (project.findProperty("zentrale.distribution") as String?)
    ?: System.getenv("ZENTRALE_DISTRIBUTION")
    ?: "direct"

android {
    namespace = "de.zentrale.zen_mobile"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        // Erinnerungen (flutter_local_notifications) brauchen java.time auch
        // auf älterem Android: Desugaring.
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    buildFeatures {
        buildConfig = true
    }

    signingConfigs {
        releaseKey?.let { key ->
            create("release") {
                val store = File(key.getProperty("storeFile") ?: "zentrale-release.jks")
                storeFile = if (store.isAbsolute) store else File(releaseKeyFile.parentFile, store.path)
                storePassword = key.getProperty("storePassword")
                keyAlias = key.getProperty("keyAlias")
                keyPassword = key.getProperty("keyPassword")
            }
        }
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "de.zentrale.zen_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        buildConfigField("boolean", "SELF_UPDATE", (distribution != "play").toString())
    }

    buildTypes {
        release {
            signingConfig = if (releaseKey != null) {
                signingConfigs.getByName("release")
            } else {
                logger.warn(
                    "WARNING: no release key at ${releaseKeyFile.path} — the release APK is signed " +
                        "with the DEBUG key. Do not publish it (see memory/system/zen_mobile.md, Self-update)."
                )
                signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.4")
    // FileProvider for handing the downloaded update to the package installer.
    implementation("androidx.core:core:1.13.1")
}
