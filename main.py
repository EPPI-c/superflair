from collections.abc import Callable
import asyncpraw
import sqlite3
import asyncio
import re
import time
import aioconsole

from dataclasses import dataclass

def is_background_task(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError as e:
            print(e)
        except Exception as e:
            print(e)
    return wrapper

@dataclass
class Flairer:
    conn: sqlite3.Connection
    reddit: asyncpraw.Reddit
    subreddit: str
    robo: str
    pattern = re.compile(r'\*\*(.*?)\*\*.*?(\"English: (.*?)\")?\)')

    @is_background_task
    async def flairing(self):
    # async def flairing(self, robo_mode=False):
        func = self.from_robo_comments
        provider = await self.reddit.redditor(self.robo)
        # if robo_mode:
        #     func = self.from_robo_comments
        #     provider = await self.reddit.redditor(self.robo)
        # else:
        #     func = self.from_sub_comments
        #     provider = await self.reddit.subreddit(self.subreddit)
        async for self.comment in provider.stream.comments():
            self.parent_comment = await self.reddit.comment(self.comment.parent_id)
            await func()

    async def from_robo_comments(self) -> bool|None:
        s = self.comment.submission
        await s.load()
        if self.comment.subreddit != self.subreddit or s.removed:
            return False
        print(f'----------------------------\n{self.comment.author}-{self.comment.id}-{self.comment.created_utc}\n{self.comment.body}\n\n')
        await self.sauce_it()

    # async def from_sub_comments(self) -> bool|None:
    #     if (not ('{oc}' in  self.comment.body.lower() and self.comment.is_submitter)) and self.comment.author.name != self.robo:
    #         print('not processed\n\n')
    #         return False
    #     await self.sauce_it()

    async def sauce_it(self):
        await self.save_sauce()
        dont_flair = re.search(r'!{.*}', self.parent_comment.body)
        if ((not await self.has_op_sauce()) or self.parent_comment.is_submitter) and self.sauces and not dont_flair:
            sauce = await self.__assemble_sauce_flair()
            await self.flair_it(sauce)

    async def has_op_sauce(self) -> bool:
        'returns true if original poster has added sauce'
        cursor = self.conn.cursor()
        res = cursor.execute(f'select * from comments where op=1 and post_id=?', (self.comment.submission.id,))
        exists = not res.fetchone() is None
        cursor.close()
        return exists

    async def parse_robo_comment(self) -> list[tuple[str, str]] | None:
        results = [(i[0],i[2]) for i in self.pattern.findall(self.comment.body)]
        return results if results else None

    async def flair_it(self, flair):
        await self.comment.submission.mod.flair(flair[:64])

    async def save_sauce(self):
        self.sauces = await self.parse_robo_comment()
        query = 'insert or ignore into comments (comment_id, parent_id, op, post_id, created_utc) values(?, ?, ?, ? ,?)'
        self.conn.execute(query, (self.comment.id, self.comment.parent_id, self.parent_comment.is_submitter, self.comment.submission.id, self.comment.created_utc))
       # query = 'insert or ignore into sauces(comment_id, sauce) values'
       # query = f'{query}{" ".join(("(?, ?)" for _ in self.sauces))}'
       # print(f'query: {query}')
       # vars = []
       # for s in self.sauces:
       #     vars.append(comment.id)
       #     vars.append(s)
       # print(f'vars: {vars}')
       # self.conn.execute(query, vars)
       # print('sauce saved')

    async def __assemble_sauce_flair(self) -> str:
        if not self.sauces: return ''
        flair = ''
        for sauce_jp, sauce_en in self.sauces:
            sauce = sauce_en if sauce_en else sauce_jp
            flair = f'{flair}{sauce}|'
        return flair[:-1]

class FlairBot:
    def __init__(self, db:str = '../flair_volume/database') -> None:
        database_scheme = ('''
        create table if not exists posts (
                post_id text not null,
                title text not null,
                created_utc int not null,
                verified int default 0,
                spoiler int default 0,
                primary key(post_id)
                );
        ''',
        '''
        create table if not exists comments (
                comment_id text not null,
                parent_id text not null,
                op integer not null default 0,
                post_id text not null unique,
                created_utc int not null,
                primary key(comment_id)
                );
        ''',
        '''
        create table if not exists sauces (
                comment_id text not null,
                sauce text,
                foreign key(comment_id) references comments(comment_id),
                primary key(sauce)
                );
        ''')
        self.conn = sqlite3.connect(db)
        self.reddit = asyncpraw.Reddit('iiep')
        self.subreddit = 'eppistoolbox'
        self.robo = 'roboragi'
        self.flairer = Flairer(self.conn, self.reddit, self.subreddit, self.robo)
        for query in database_scheme:
            self.conn.execute(query)


    @is_background_task
    async def collect_posts(self):
        print ('collecting start')
        subreddit = await self.reddit.subreddit(self.subreddit)
        async for submission in subreddit.stream.submissions():
            await self.save_post(submission)
            print (f'{submission.title} collected')

    # is a background task
    async def no_sauce_hook(self, action:Callable, after=1200, frequency=30, spoiler=True):
        cursor = None
        try:
            cursor = self.conn.cursor()
            while True:
                print('no_sauce_hook')
                await asyncio.sleep(frequency)
                query = 'SELECT post_id, title, spoiler FROM posts WHERE created_utc < ? AND verified=0' 
                value = time.time() - after
                res = cursor.execute(query, (value,))
                ids = []
                placeholder = ''
                for post_id in res:
                    post_id, title, spoiler = post_id
                    await action(post_id)
                    if spoiler: await self.remove_post_for_spoiler(post_id, title)
                    ids.append(post_id)
                    placeholder = f'{placeholder}?,'
                placeholder = placeholder.removesuffix(',')
                query = f'UPDATE posts SET verified=1 WHERE post_id IN ({placeholder})'
                cursor.execute(query, (*ids,))
        except asyncio.CancelledError as e:
            print(e)
        except Exception as e:
            print(e)
        finally:
            if cursor: cursor.close()

    async def comment_no_sauce(self, post_id):
        print(f'commented on {post_id}')
        post = await self.reddit.submission(post_id)
        comment = await post.reply("Hi there please consider sourcing your post with \"{anime name}\"")
        if not comment: 
            return False
        await comment.mod.distinguish(sticky=True)

    async def remove_post_for_no_sauce(self, post_id):
        await self.remove_post(post_id, flair_template_id='094ce764-898a-11e9-b1bf-0e66eeae092c')

    async def remove_post_for_spoiler(self, post_id, title):
        if not re.search(r'.*\[.*\].*', title):
            await self.remove_post(post_id, flair_template_id='094ce764-898a-11e9-b1bf-0e66eeae092c')

    async def remove_post(self, post_id, flair_template_id=None, text=None):
        post = await self.reddit.submission(post_id)
        await post.mod.remove()
        await post.mod.flair(flair_template_id=flair_template_id, text=text)

    async def save_post(self, post):
        query = 'insert or ignore into posts (post_id, created_utc, spoiler, title) values(?, ?, ?, ?)'
        values = (post.id, post.created_utc, post.spoiler, post.title)
        self.conn.execute(query, values)


async def main():
    bot = FlairBot(':memory:')
    flairing = asyncio.create_task(bot.flairer.flairing())
    saving_posts = asyncio.create_task(bot.collect_posts())
    no_sauce_hook = asyncio.create_task(bot.no_sauce_hook(bot.comment_no_sauce, frequency=120, spoiler=False))
    await aioconsole.ainput('press anything to stop')
    await flairing
    await saving_posts
    await no_sauce_hook

if __name__ == "__main__":
    asyncio.run(main())
