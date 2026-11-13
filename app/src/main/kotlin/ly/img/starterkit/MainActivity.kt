package ly.img.starterkit

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import ly.img.editor.configuration.memories.MemoriesApp
import ly.img.editor.configuration.memories.MemoriesViewModel
import ly.img.editor.core.theme.EditorTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        // Enable immersive mode compatibility
        WindowCompat.setDecorFitsSystemWindows(window, false)

        setContent {
            val viewModel: MemoriesViewModel = viewModel()
            val isFullscreen by viewModel.isFullscreen.collectAsState()

            // Handle fullscreen state changes
            LaunchedEffect(isFullscreen) {
                val windowInsetsController = WindowCompat.getInsetsController(window, window.decorView)
                if (isFullscreen) {
                    // Hide system UI (status bar and navigation bar)
                    windowInsetsController.hide(
                        WindowInsetsCompat.Type.statusBars() or WindowInsetsCompat.Type.navigationBars(),
                    )
                    windowInsetsController.systemBarsBehavior =
                        WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
                } else {
                    // Show system UI
                    windowInsetsController.show(
                        WindowInsetsCompat.Type.statusBars() or WindowInsetsCompat.Type.navigationBars(),
                    )
                }
            }

            EditorTheme {
                Surface {
                    MemoriesApp(
                        license = null, // pass your license, or null for evaluation mode (watermark)
                        onExit = { finish() },
                        viewModel = viewModel,
                    )
                }
            }
        }
    }
}
