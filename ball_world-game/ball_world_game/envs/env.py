import gym
from gym import spaces
import pygame
import numpy as np
import pygame, random
from pygame.locals import *
import random

# For test code
# from Object import Ball, Rectangle, Collision

# For test AI
# from ball_world_game.envs.Object import Ball, Rectangle, Collision

# For setup.py install
# from ball_world_game.envs.Object import Ball, Rectangle, Collision
try:
    from Object import Ball, Rectangle, Collision
except: 
    None

try:
    from ball_world_game.envs.Object import Ball, Rectangle, Collision
except:
    None


class CustomEnv(gym.Env):
    metadata = { "render_fps": 120}
    
    def __init__(self, render_mode=None, num_of_obs=10, num_of_br=5, num_of_acc=1, ball_initial_speed=6):
        assert num_of_obs >= 5
        assert num_of_br >= 1
        assert num_of_acc >= 0
        assert ball_initial_speed > 1

        super().__init__()
        self.action_space = gym.spaces.Discrete(3)           #left, right, stay
        max_speed = 20
        upper_bound = []
        lower_bound = []

        self.num_of_obs = num_of_obs
        self.num_of_br = num_of_br
        self.num_of_acc = num_of_acc
        # initialize the bounding box for state
        # the two 0s is for padding [making it as shape (4)]
        speed_lower_bound = np.array([-max_speed, -max_speed, 0, 0]).reshape(1, 4)
        speed_upper_bound = np.array([max_speed, max_speed, 0, 0]).reshape(1, 4)

        lower_bound.append(speed_lower_bound)
        upper_bound.append(speed_upper_bound)

        # the x, y coordinates of objects have 0 as lower bound
        screen_lower_bound = np.array([0, 0, 0, 0]).repeat(2+self.num_of_obs+self.num_of_br+self.num_of_acc).reshape(-1, 4)
        lower_bound.append(screen_lower_bound)
        # the x, y coordinate of objects has 450, 800 as upper bound respectively
        screen_upper_bound = np.array([450, 800, 450, 800]).repeat(2+self.num_of_obs+self.num_of_br+self.num_of_acc).reshape(-1, 4)
        upper_bound.append(screen_upper_bound)
        # flatten np array
        lower_bound = np.concatenate(lower_bound, axis=None)
        upper_bound = np.concatenate(upper_bound, axis=None)
        # initialize observation space
        self.observation_space = spaces.box.Box(low=lower_bound, high=upper_bound, shape=((3+self.num_of_obs+self.num_of_br+self.num_of_acc)* 4,), dtype=np.float32)

        # screen dimension
        self.SCREEN_WIDTH = 450
        self.SCREEN_HEIGHT = 800

        # game ending flags: win or lose
        self.terminated = False
        self.win = False

        # record the starting and ending time
        self.start_time = None
        self.end_time = None

        self.render_mode = render_mode
        self.clock = None
        self.screen = None
        self.rng = self.np_random

        # font initialize
        pygame.font.init()
        self.font_small = pygame.font.Font("ball_world-game/ball_world_game/envs/breakout_font.ttf",20)
        self.font_large = pygame.font.Font("ball_world-game/ball_world_game/envs/breakout_font.ttf", 36)

        self.previous_obs_collision = -1
        self.initial_speed = ball_initial_speed

        self.main_back = pygame.image.load('ball_world-game/ball_world_game/envs/Image/Main_background.jpg')

        # Sound initialize
        pygame.mixer.init()
        self.end_play = False
        self.at_end_page = False
        # Train mode mute sound
        if self.render_mode == 'train':
            self.sound_hit_obs = None
            self.sound_hit_brake = None
            self.sound_hit_acc = None
            self.sound_hit_bar = None
        else:
            self.sound_hit_obs = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/Hit_Obstacle.mp3')
            self.sound_hit_brake = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/Hit_Brake.mp3')
            self.sound_hit_acc = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/Hit_Accelerator.mp3')
            self.sound_hit_bar = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/sound_hit_bar.wav')


    def _get_info(self):
        return {"relative pos": ((np.array(self.ball.rect.center) - np.array(self.bar.rect.center))**2).sum(),
                }
    def render(self):
        # to avoid windows not responding
        if self.render_mode == 'train' or self.render_mode == 'test':
            pygame.event.get()

        if self.clock is None and self.render_mode != 'train':
            self.clock = pygame.time.Clock()

        self.screen.fill((0, 0, 0))
        self.screen.blit(self.main_back, (0,0))

        # draw objects
        self.ball.draw(self.screen)
        self.bar.draw(self.screen)

        for obstacle in self.obstacles:
            obstacle.draw(self.screen)

        for brake in self.brake:
            brake.draw(self.screen)

        for accelerator in self.accelerators:
            accelerator.draw(self.screen)

        # Show time, speed and strength
        # Only display when mode is not 'train'
        if self.render_mode != 'train':
            self.speed_show = self.font_small.render('Speed: ' + '{:.2f}'.format(np.sqrt(self.ball.speed[0]**2 + self.ball.speed[1]**2)), True, (255,150,0))
            self.screen.blit(self.speed_show, (10,10))
            cur_time = pygame.time.get_ticks()
            survived_time = (cur_time - self.start_time) / 1000
            sur_time_message = self.font_small.render('time: '+ "{:.1f}".format(survived_time) + 's', True, (255,150,0))
            self.screen.blit(sur_time_message, (150,10))
            strength = 5 - self.ball.count
            strength_message = self.font_small.render(f'strength: {strength}', True, (255,150,0))
            self.screen.blit(strength_message, (300,10))

        if self.render_mode != 'train' and self.terminated != True:
            pygame.display.update()
            self.clock.tick(CustomEnv.metadata['render_fps'])
            pygame.display.flip()

    def get_state(self):
        # our state consists of object speed and position with shape 4
        # For speed, we have [speed_x, speed_y, 0, 0]
        # For position, we have [top_left_x, top_left_y, right_bottom_x, right_bottom_y]
        state = []
        state.append([self.ball.speed[0], self.ball.speed[1], 0, 0])
        # ball coordinates
        ball_coor_state = np.array(self.ball.rect)
        ball_coor_state[2:4] += self.ball.rect[0:2]
        state.append(ball_coor_state)

        # bar coordinates
        bar_coor_state = np.array(self.bar.rect)
        bar_coor_state[2:4] += self.bar.rect[0:2]
        state.append(bar_coor_state)

        # obstacle coordinates
        for obstacle in self.obstacles:
            one_obs_coor = np.array(obstacle.rect)
            one_obs_coor[2:4] += obstacle.rect[0:2]
            state.append(one_obs_coor)

        # brake coordinates
        for brake in self.brake:
            one_obs_coor = np.array(brake.rect)
            one_obs_coor[2:4] += brake.rect[0:2]
            state.append(one_obs_coor)

        # accelerator coordinates
        for accelerator in self.accelerators:
            one_obs_coor = np.array(accelerator.rect)
            one_obs_coor[2:4] += accelerator.rect[0:2]
            state.append(one_obs_coor)

        state = np.concatenate(state,0).reshape(-1,4)

        return state.reshape(-1)

    
    def step(self, action):
        # update bar position
        self.bar.update(action)
        # update ball position and check bar collision
        dist = self.ball.update(self.bar, self.sound_hit_bar)

        # a counter for reward of hitting objects
        hit_brake = 0

        # reward for hitting brake
        for br in self.brake:
            if br.update(self.ball,self.rng, self.sound_hit_brake):
                new_brake = Rectangle.Brake(self.SCREEN_WIDTH, self.rng)
                while pygame.sprite.spritecollide(new_brake, self.obstacles, False) or pygame.sprite.spritecollide(new_brake, self.brake, False):
                    new_brake = Rectangle.Brake(self.SCREEN_WIDTH, self.rng)
                self.brake.add(new_brake)
                hit_brake += 1
                self.ball.count += 1

        # penalty for hitting accelerator
        for acc in self.accelerators:
            if acc.update(self.ball,self.rng, self.sound_hit_acc):
                new_acc = Rectangle.Accelerator(self.SCREEN_WIDTH, self.rng)

                self.accelerators.add(new_acc)
                self.ball.count = max(0, self.ball.count-1)
                hit_brake -= 10

        self.previous_obs_collision = Collision.ball_collide_with_obstacles(self.ball, self.obstacles, self.previous_obs_collision, self.rng)
        if self.previous_obs_collision != -1 and self.sound_hit_bar is not None:
            self.sound_hit_obs.play()

        # update terminate flag
        self.terminated = (not self.ball.survive) or self.ball.win
        # calculate reward
        reward = dist if self.ball.survive else -10000000
        reward += hit_brake * 2000
        if self.ball.win == True:
            reward += 10000000

        # get observation
        observation = self.get_state()
        # get info
        info = self._get_info()

        if self.render_mode != 'train':
            self.render()

        if self.terminated == True and self.render_mode == 'human' and self.at_end_page == False:
            self.end_page()
            self.end_play = False
            self.at_end_page = False
            self.end_time = None

        return observation, reward, self.terminated, info


        

    def reset(self, seed=1, options=None):
        super().reset(seed=seed)
        # use np_random as the random generator
        self.rng = self.np_random
            
        # create screen
        if self.screen == None:
            pygame.init()
            if self.render_mode != 'train':
                pygame.display.init()
                # show screen for non-train mode
                display_flag = pygame.SHOWN
                self.screen = pygame.display.set_mode([self.SCREEN_WIDTH, self.SCREEN_HEIGHT], flags=display_flag)
            else:
                # hide screen for train mode
                display_flag = pygame.HIDDEN
                self.screen = pygame.display.set_mode([self.SCREEN_WIDTH, self.SCREEN_HEIGHT], flags=display_flag)

        # start_page
        if self.render_mode == 'human':
            self.start_page()
        else:
            self.start_time = pygame.time.get_ticks()

        # Initialize Objects
        self.ball = Ball.Ball(self.SCREEN_WIDTH, self.SCREEN_HEIGHT, self.screen, self.rng, self.initial_speed)
        self.bar = Rectangle.ControlBar((225, 650), 70, 10, self.SCREEN_WIDTH, self.SCREEN_HEIGHT)
        self.obstacles = [Rectangle.Obstacle(self.SCREEN_WIDTH, self.rng) for i in range(self.num_of_obs)]

        self.brake = []
        for i in range(self.num_of_br):
            brake = Rectangle.Brake(self.SCREEN_WIDTH, self.rng)
            while pygame.sprite.spritecollide(brake, self.obstacles, False) or pygame.sprite.spritecollide(brake, self.brake, False):
                brake = Rectangle.Brake(self.SCREEN_WIDTH, self.rng)
            self.brake.append(brake)
        self.brake = pygame.sprite.Group(self.brake)

        self.accelerators = []
        for i in range(self.num_of_acc):
            acc = Rectangle.Accelerator(self.SCREEN_WIDTH, self.rng)
            while pygame.sprite.spritecollide(acc, self.obstacles, False) or pygame.sprite.spritecollide(acc, self.brake, False) or pygame.sprite.spritecollide(acc, self.accelerators, False):
                acc = Rectangle.Accelerator(self.SCREEN_WIDTH, self.rng)
            self.accelerators.append(acc)
        self.accelerators = pygame.sprite.Group(self.accelerators)

        state = self.get_state()
        info =self._get_info()

        
        self.render()
              
        return state

    def start_page(self):
        self.start_bg_sound = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/Starting_page.mp3')
        self.start_bg_sound.play(-1)
        start = False
        self.screen.fill((0, 0, 0))
        while not start:
            # check close start page
            for event in pygame.event.get():
                    if event.type == KEYDOWN:
                        if event.key == K_SPACE:
                            start = True
            
            start_game_message_1 = self.font_small.render('Welcome to ', True, (255,255,0))
            self.screen.blit(start_game_message_1, (150,300))

            start_game_message_2 = self.font_large.render('BreakDown ', True, (255,255,255))
            self.screen.blit(start_game_message_2, (120,350))

            start_game_message_3 = self.font_small.render('Press SPACEBAR to start', True, (255,255,0))
            self.screen.blit(start_game_message_3, (90,430))
            pygame.display.update()
            pygame.display.flip()
        self.start_time = pygame.time.get_ticks()
        self.start_bg_sound.stop()
        self.main_bg_sound = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/Main_game.mp3')
        self.main_bg_sound.play(-1)


    def end_page(self):
        self.at_end_page = True
        self.main_bg_sound.stop()
        if self.end_play == False:
            self.win_bf_sound = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/win.wav')
            self.lose_bf_sound = pygame.mixer.Sound('ball_world-game/ball_world_game/envs/Music/lose.wav')
        if self.end_time == None:
            self.end_time = pygame.time.get_ticks()
        total_time = (self.end_time - self.start_time) / 1000
        self.ball.speed = [0,0]
        for acc in self.accelerators: acc.speed = [0,0]
        exit_game = False
        while not exit_game:
            # check close end page
            for event in pygame.event.get():
                    if event.type == KEYDOWN:
                        if event.key == K_ESCAPE:
                            exit_game = True

            self.screen.fill((0,0,0))
            end_game_message_time = self.font_small.render('Survived time: '+ "{:.1f}".format(total_time) + 's', True, (255,255,255))
            self.screen.blit(end_game_message_time, (130,450))

            # display wordings for the result
            if self.ball.win == True:
                if self.end_play == False:
                    self.win_bf_sound.play()
                end_win = "You Win! :)"
                end_win_2 = "The ball slows down!"
            else:
                if self.end_play == False:
                    self.lose_bf_sound.play()
                end_win = "You Lose! :("
                if self.ball.too_fast == True:
                    end_win_2 = "The ball is too fast!"
                else:
                    end_win_2 = "The ball escaped! Bye!"

            self.end_play = True
            end_game_message_1 = self.font_large.render(end_win, True, (255,255,0))
            self.screen.blit(end_game_message_1, (125,350))
            end_game_message_2 = self.font_small.render(end_win_2, True, (255,255,255))
            self.screen.blit(end_game_message_2, (120,410))
            end_game_message_3 = self.font_small.render('Press ESC to leave the game', True, (255,255,0))
            self.screen.blit(end_game_message_3, (75,490))
            pygame.display.update()
            self.clock.tick(CustomEnv.metadata['render_fps'])
            pygame.display.flip()

    def close(self):
        if self.screen is not None:
            pygame.display.quit()
            pygame.quit()





# ######### Test code ########
# if __name__ == '__main__':
#     #print("HI")
#     test = CustomEnv(render_mode='human')
#     running = True
#
#     test.reset()
#     while running:
#         pressed_keys = pygame.key.get_pressed()
#         action = 1
#         if pressed_keys[K_LEFT]:
#             action = 0
#         if pressed_keys[K_RIGHT]:
#             action = 2
#
#         ob, rew, terminated, info = test.step(action)
#
#
#
#         for event in pygame.event.get():
#             if event.type == KEYDOWN:
#                 if event.key == K_ESCAPE:
#                     test.close()
#                     running = False
#