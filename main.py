import asyncpraw
import sqlite3
import asyncio
import re
import time

def is_background_task(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError as e:
            print(e)
    return wrapper

class FlairBot():
    def __init__(self, db:str = '../flair_volume/database') -> None:
        database_scheme = ('''
        create table if not exists posts (
                post_id text not null,
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
        self.patternJ = re.compile(r'(?<=\*\*).*(?=\*\*)')
        self.patternE = re.compile(r'(?<="English: ).*?(?=")')
        self.subreddit = 'animemes'
        self.robo = 'roboragi'
        self.reddit = asyncpraw.Reddit('iiep')
        self.conn = sqlite3.connect(db)
        for query in database_scheme:
            self.conn.execute(query)

    @is_background_task
    async def flairing(self, robo_mode=False):
        if robo_mode:
            func = self.from_robo_comments
            provider = await self.reddit.redditor(self.robo)
        else:
            func = self.from_sub_comments
            provider = await self.reddit.subreddit(self.subreddit)
        async for comment in provider.stream.comments():
            print(f'----------------------------\n{comment.author}-{comment.id}-{comment.created_utc}\n{comment.body}\n\n')
            await func(comment)

    @is_background_task
    async def collect_posts(self):
        subreddit = await self.reddit.subreddit(self.subreddit)
        async for submission in subreddit.stream.submissions():
            await self.save_post(submission)

    async def remove_no_after(self, after=30, frequency=30, spoiler=True):
        cursor = None
        try:
            cursor = self.conn.cursor()
            while True:
                await asyncio.sleep(frequency)
                query = 'SELECT post_id, title FROM posts WHERE created_utc < ? AND verified=0' 
                if spoiler: query = f'{query} AND spoiler=1'
                value = time.time() - after
                res = cursor.execute(query, (value,))
                ids = ''
                for post_id in res:
                    post_id, title = post_id
                    await self.remove_post_for_spoiler(post_id, title) if spoiler else await self.remove_post_for_no_sauce(post_id)
                    ids = f'{ids}{post_id}, '
                query = 'UPDATE posts SET verified=1 WHERE post_id IN (?)'
                cursor.execute(query, (ids,))
        except asyncio.CancelledError as e:
            print(e)
        except Exception as e:
            print(e)
        finally:
            if cursor: cursor.close()

    async def remove_post_for_no_sauce(self, post_id):
        await self.remove_post(post_id, flair_template_id='094ce764-898a-11e9-b1bf-0e66eeae092c')

    async def remove_post_for_spoiler(self, post_id, title):
        if not re.search(r'.*\[.*\].*', title):
            await self.remove_post(post_id, flair_template_id='094ce764-898a-11e9-b1bf-0e66eeae092c')

    async def remove_post(self, post_id, flair_template_id=None, text=None):
        post = await self.reddit.submission(post_id, flair_template_id=flair_template_id, text=text)
        await post.mod.remove()
        await post.mod.flair(flair_template_id=flair_template_id, text=text)

    async def from_robo_comments(self, comment) -> bool|None:
        s = comment.submission
        await s.load()
        if comment.subreddit != self.subreddit or s.removed:
            print('not processed\n\n')
            return False
        await self.sauce_it(comment)

    async def from_sub_comments(self, comment) -> bool|None:
        if (not ('{oc}' in  comment.body.lower() and comment.is_submitter)) and comment.author.name != self.robo:
            print('not processed\n\n')
            return False
        await self.sauce_it(comment)

    async def has_op_sauce(self, comment) -> bool:
        'returns true if original poster has added sauce'
        cursor = self.conn.cursor()
        res = cursor.execute(f'select * from comments where op=1 and post_id=?', (comment.submission.id,))
        exists = not res.fetchone() is None
        cursor.close()
        return exists

    async def is_op(self, comment) -> int:
        'returns true if sauce was requested by original poster'
        parent_comment = await self.reddit.comment(comment.parent_id)
        return 1 if parent_comment.is_submitter else 0

    async def sauce_it(self, comment):
        await self.save_sauce(comment)
        if ((not await self.has_op_sauce(comment)) or await self.is_op(comment)) and self.sauces:
            sauce = await self.assemble_sauce_flair()
            await self.flair_it(comment, sauce)

    async def assemble_sauce_flair(self) -> str:
        flair = ''
        for sauce_jp, sauce_en in self.sauces:
            sauce = sauce_en if sauce_en else sauce_jp
            flair = f'{flair}{sauce}|'
        return flair[:-1]

    async def parse_robo_comment(self, comment):
        entries = comment.body.split('\n\n')
        del entries[1::2]
        del entries[-1]
        results = [(c.group() if (c := re.search(self.patternJ, i)) else None, c.group() if (c := re.search(self.patternE, i)) else None) for i in entries]
        return results if results else ['oc']

    async def flair_it(self, comment, flair):
        await comment.submission.mod.flair(flair[:64])

    async def save_sauce(self, comment):
        self.sauces:list = await self.parse_robo_comment(comment)
        query = 'insert or ignore into comments (comment_id, parent_id, op, post_id, created_utc) values(?, ?, ?, ? ,?)'
        self.conn.execute(query, (comment.id, comment.parent_id, await self.is_op(comment), comment.submission.id, comment.created_utc))
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

    async def save_post(self, post):
        query = 'insert or ignore into posts (post_id, created_utc, spoiler) values(?, ?, ?)'
        values = (post.id, post.created_utc, post.spoiler)
        self.conn.execute(query, values)


async def main():
    bot = FlairBot(':memory:')
    saving_posts = asyncio.create_task(bot.collect_posts())
    removing_post = asyncio.create_task(bot.remove_no_after(spoiler=False))
    

if __name__ == "__main__":
    asyncio.run(main())
