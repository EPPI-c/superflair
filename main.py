import asyncpraw
import sqlite3
import asyncio
import re

class FlairBot():
    def __init__(self, db:str = '../flair_volume/database') -> None:
        database_scheme = ('''
        CREATE TABLE IF NOT EXISTS posts (
                post_id TEXT NOT NULL,
                created_utc INT NOT NULL,
                PRIMARY KEY(post_id)
                );
        ''',
        '''
        CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                op INTEGER NOT NULL DEFAULT 0,
                post_id TEXT NOT NULL UNIQUE,
                created_utc INT NOT NULL,
                PRIMARY KEY(comment_id)
                );
        ''',
        '''
        CREATE TABLE IF NOT EXISTS sauces (
                comment_id TEXT NOT NULL,
                sauce TEXT,
                FOREIGN KEY(comment_id) REFERENCES comments(comment_id),
                PRIMARY KEY(sauce)
                );
        ''')
        self.subreddit = 'Animemes'
        self.robo = 'Roboragi'
        self.reddit = asyncpraw.Reddit('iiep')
        self.conn = sqlite3.connect(db)
        for query in database_scheme:
            self.conn.execute(query)

    async def start(self, robo_mode=False):
        if robo_mode:
            func = self.from_robo_comments
            provider = await self.reddit.redditor(self.robo)
        else:
            func = self.from_sub_comments
            provider = await self.reddit.subreddit(self.subreddit)

        async for i in provider.stream.comments():
            global flairbot_on
            if not flairbot_on:
                print('STOPPING')
                break
            print(f'----------------------------\n{i.author}-{i.id}-{i.created_utc}\n{i.body}\n\n')
            await func(i)

    async def from_robo_comments(self, comment):
        s = comment.submission
        await s.load()
        if comment.subreddit != self.subreddit or s.removed:
            print('not processed\n\n')
            return False

        await self.sauce_it(comment)

    async def from_sub_comments(self, comment):
        if (not ('{oc}' in  comment.body.lower() and comment.is_submitter)) and comment.author.name != self.robo:
            print('not processed\n\n')
            return False

        await self.sauce_it(comment)

    async def has_op_sauce(self, comment):
        'returns True if Original Poster has added sauce'
        cursor = self.conn.cursor()
        res = cursor.execute(f'SELECT * FROM comments WHERE op=1 AND post_id=?', (comment.submission.id,))
        exists = not res.fetchone() is None
        cursor.close()
        return exists

    async def is_op(self, comment):
        'returns True if sauce was requested by Original Poster'
        parent_comment = await self.reddit.comment(comment.parent_id)
        return 1 if parent_comment.is_submitter else 0

    async def sauce_it(self, comment):
        await self.save_sauce(comment)
        if ((not await self.has_op_sauce(comment)) or await self.is_op(comment)) and self.sauces:
            await self.flair_it(comment, self.sauces[0])

    async def parse_robo_comment(self, comment):
        pattern = r'(?<=\*\*).*(?=\*\*)'
        results = re.findall(pattern, comment.body)
        return results if results else ['OC']

    async def flair_it(self, comment, flair):
        await comment.submission.mod.flair(flair[:64])
        print('flaired')

    async def save_sauce(self, comment):
        self.sauces:list = await self.parse_robo_comment(comment)
        query = 'INSERT OR IGNORE INTO comments (comment_id, parent_id, op, post_id, created_utc) VALUES(?, ?, ?, ? ,?)'
        self.conn.execute(query, (comment.id, comment.parent_id, await self.is_op(comment), comment.submission.id, comment.created_utc))
       # query = 'INSERT OR IGNORE INTO SAUCES(comment_id, sauce) VALUES'
       # query = f'{query}{" ".join(("(?, ?)" for _ in self.sauces))}'
       # print(f'query: {query}')
       # vars = []
       # for s in self.sauces:
       #     vars.append(comment.id)
       #     vars.append(s)

#        print(f'vars: {vars}')
#        self.conn.execute(query, vars)
#        print('sauce saved')

    async def save_post(self, i):
        print(i)

async def main():
    bot = FlairBot()
    await bot.start(robo_mode=True)

if __name__ == "__main__":
    asyncio.run(main())
