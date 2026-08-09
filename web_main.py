"""浏览器专用入口：运行完全相同的 game.py，只在每帧让出浏览器事件循环。"""
from pathlib import Path
import asyncio

source_path = Path(__file__).with_name("game.py")
source = source_path.read_text(encoding="utf-8")
source = source.replace(
    "def run_game(test_mode=False):",
    "async def run_game(test_mode=False):",
    1,
)
source = source.replace(
    "        pygame.display.flip()\n",
    "        pygame.display.flip()\n        await asyncio.sleep(0)\n",
)
source = source.replace(
    "    run_game()\n",
    "    asyncio.run(run_game())\n",
)
namespace = {"__name__": "__main__", "__file__": str(source_path), "asyncio": asyncio}
exec(compile(source, str(source_path), "exec"), namespace)
