import asyncpraw
import sqlite3
import asyncio

SUBREDDIT = 'eppistoolbox'
ROBO = 'roboragi'
REDDIT =  asyncpraw.Reddit('iiep')

database_scheme = '''
CREATE TABLE posts IF NOT EXISTS (
        post_id TEXT NOT NULL,
        created_utc INT NOT NULL,
        PRIMARY KEY(post_id)
        )
CREATE TABLE sauces IF NOT EXISTS (
        comment_id TEXT NOT NULL,
        parent_id TEXT NOT NULL,
        op BOOL NOT NULL DEFAULT False,
        post_id TEXT NOT NULL,
        create_utc INT NOT NULL,
        FOREIGN KEY(post_id, posts)
        PRIMARY KEY(comment_id)
        )
'''
select_sauces = '''
SELECT count(*) FROM sauces WHERE op = True AND post_id =
'''
insert_sauce = '''
INSERT INTO comments
'''
def has_op_sauce(i):
    pass

async def get_robo_comments():
    redditor = await REDDIT.redditor(ROBO)
    async for i in redditor.stream.comments():
        # await sauce_it(i)
        print(i)

async def sauce_it(i):
    await save_sauce(i)
    if i.subreddit != SUBREDDIT:
        return False
    if i.author == i.post.author:
        return await flair_it(i)
    if not has_op_sauce(i):
        return await sauce_it(i)

async def flair_it(i):
    pass

async def save_sauce(i):
    pass

async def save_post(i):
    pass

async def get_posts():
    sub = await REDDIT.subreddit(SUBREDDIT)
    async for i in sub.stream.submissions():
        await save_post(i)

if __name__ == "__main__":
    asyncio.run(get_robo_comments())
