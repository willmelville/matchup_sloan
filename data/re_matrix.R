library(abdwr3edata)
library(baseballr)
library(readr)
library(here)
library(purrr)
library(dplyr)
library(tidyr)

retro_data <- retrosheet_data(here::here('retrosheet'), c(2022, 2021, 2020, 2019,2023))
retro2016 <- retro_data |> pluck('2023') |> pluck('events')
retro2017 <- retro_data |> pluck('2019') |> pluck('events')
retro2018 <- retro_data |> pluck('2022') |> pluck('events')
retro2019 <- retro_data |> pluck('2021') |> pluck('events')
retro2015 <- retro_data |> pluck('2020') |> pluck('events')
#combine
retro2016 <- rbind(retro2016, retro2017, retro2018, retro2019, retro2015)
#memory management
rm(retro2015, retro2017, retro2018, retro2019)

retro2016 <- retro2016 |> 
  mutate(
    runs_before = away_score_ct + home_score_ct,
    half_inning = paste(game_id, inn_ct, bat_home_id),
    runs_scored = 
      (bat_dest_id > 3) + (run1_dest_id > 3) + 
      (run2_dest_id > 3) + (run3_dest_id > 3)
  )


half_innings <- retro2016 |>
  group_by(half_inning) |>
  summarize(
    outs_inning = sum(event_outs_ct), 
    runs_inning = sum(runs_scored),
    runs_start = first(runs_before),
    max_runs = runs_inning + runs_start
  )


retro2016 <- retro2016 |>
  inner_join(half_innings, by = "half_inning") |>
  mutate(runs_roi = max_runs - runs_before)

retro2016 <- retro2016 |>
  mutate(
    bases = paste0(
      if_else(base1_run_id == "", 0, 1),
      if_else(base2_run_id == "", 0, 1),
      if_else(base3_run_id == "", 0, 1)
    ),
    state = paste(bases, outs_ct)
  )

retro2016 <- retro2016 |>
  mutate(
    is_runner1 = as.numeric(
      run1_dest_id == 1 | bat_dest_id == 1
    ),
    is_runner2 = as.numeric(
      run1_dest_id == 2 | run2_dest_id == 2 | 
        bat_dest_id == 2
    ),
    is_runner3 = as.numeric(
      run1_dest_id == 3 | run2_dest_id == 3 |
        run3_dest_id == 3 | bat_dest_id == 3
    ),
    new_outs = outs_ct + event_outs_ct,
    new_bases = paste0(is_runner1, is_runner2, is_runner3),
    new_state = paste(new_bases, new_outs)
  )
#map from the state defined here to the format I have historically used
old_states <- c('000 0', '000 1', '000 2', '001 0', '001 1', '001 2',
                '010 0', '010 1', '010 2', '011 0', '011 1', '011 2',
                '100 0', '100 1', '100 2', '101 0', '101 1', '101 2', 
                '110 0', '110 1', '110 2', '111 0', '111 1', '111 2', 
                '3')
new_states <- c('___-0', '___-1', '___-2', '__3-0', '__3-1', '__3-2', 
                '_2_-0', '_2_-1', '_2_-2', '_23-0','_23-1', '_23-2', 
                '1__-0','1__-1', '1__-2', '1_3-0', '1_3-1', '1_3-2', 
                '12_-0', '12_-1','12_-2', '123-0', '123-1', '123-2', 
                '3')

retro2016[retro2016$new_outs > 2, 'new_state'] <- '3'
for (i in 1:length(old_states)){
  retro2016[retro2016$state == old_states[i], 'state'] = new_states[i]
  retro2016[retro2016$new_state == old_states[i], 'new_state'] = new_states[i]
}


changes2016 <- retro2016 |> 
  filter(state != new_state | runs_scored > 0)

changes2016_complete <- changes2016 |>
  filter(outs_inning == 3)

#I want the distribution of runs scored for the rest of the inning
cutoff <- subset(changes2016_complete, runs_roi <= 10)
state_visits <- changes2016_complete |> 
  count(state) 

run_prob_dist <- data.frame()
for (i in 1:nrow(state_visits)){
  st <- state_visits$state[i]
  t <- subset(cutoff, state == st)
  newdf <- state_visits[i,]
  for (r in 0:10){
    newdf[1,paste(as.character(r), '_runs', sep='')] <- nrow(subset(t, runs_roi == r))
  }
  run_prob_dist <- rbind(run_prob_dist, newdf)
}


write.csv(run_prob_dist, 'rp.csv')
