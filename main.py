"""Pygame 网页版固定启动入口，并在启动失败时显示真实错误。"""
import asyncio
import traceback


async def show_error(message):
    import pygame
    pygame.init()
    screen = pygame.display.set_mode((1000, 700))
    font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 21)
    lines = message.splitlines()[-18:]
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        screen.fill((24, 28, 34))
        screen.blit(font.render("WEB STARTUP ERROR", True, (255, 120, 90)), (28, 24))
        for index, line in enumerate(lines):
            screen.blit(small.render(line[:115], True, (235, 235, 235)), (28, 72 + index * 30))
        pygame.display.flip()
        await asyncio.sleep(0)


async def main():
    try:
        import game
        await game.run_game()
    except Exception:
        await show_error(traceback.format_exc())


asyncio.run(main())
